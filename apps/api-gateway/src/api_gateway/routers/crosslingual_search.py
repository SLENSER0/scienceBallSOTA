"""Cross-lingual (ru↔en) поиск + детект языка и устойчивость к OCR-шуму (§23.17).

§23.17 требует: детект языка чанка/запроса (ru/en), двуязычный/мультиязычный
поиск (ru-запрос находит en-контент и наоборот) и демонстрацию recall на
«грязном» ru-тексте с OCR-шумом. Всё это работает «как есть» на server-профиле
(Neo4j :8000), потому что активная эмбеддинг-модель уже мультиязычная —
``ibm-granite/granite-embedding-*-multilingual-r2`` (см. ``settings.embedding_model``),
и один и тот же вектор-простор покрывает и русский, и английский. Cross-lingual
поиск тут — не «перевод + моноязычный поиск», а прямое сближение ru-запроса и
en-текста в общем пространстве эмбеддингов (§4.4).

Три ручки, все read-only (граф не меняется):

* ``POST /api/v1/crosslingual/detect`` — детект языка (ru/en/mixed) для
  произвольных текстов/чанков + метрика «OCR-шума» (доля битых токенов,
  homoglyph-смешение кириллицы и латиницы внутри слова).
* ``POST /api/v1/crosslingual/search`` — семантический поиск по узлам живого
  графа мультиязычной моделью: ru-запрос честно находит en-узлы. Каждый хит
  помечен своим детектированным языком, поэтому видно cross-lingual попадания.
* ``GET  /api/v1/crosslingual/demo`` — воспроизводимая демонстрация recall на
  «грязном» ru-тексте: параллельный ru↔en мини-корпус, ru-запросы прогоняются
  как есть и с инъекцией OCR-шума; меряется recall@1/@3 en-таргета и деградация.

Никаких проприетарных LLM — только OSS эмбеддинги (ADR-0006).
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from kg_common import get_logger, get_settings
from kg_retrievers.embeddings import embed, embed_one
from kg_schema.vector_index_spec import cosine

router = APIRouter(prefix="/api/v1/crosslingual", tags=["crosslingual"])

_log = get_logger("api.crosslingual")

_CYR = re.compile(r"[а-яё]", re.I)
_LAT = re.compile(r"[a-z]", re.I)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
# Слово со смешением кириллицы и латиницы внутри — типичный след OCR/homoglyph.
_MIXED_WORD = re.compile(r"(?=.*[а-яё])(?=.*[a-z])", re.I)

_MIXED_RATIO = 0.25  # порог «mixed»: min(cyr,lat)/max(cyr,lat) выше него → mixed


# --------------------------------------------------------------------------- #
# Language detection + OCR-noise scoring                                       #
# --------------------------------------------------------------------------- #
def detect_language(text: str) -> str:
    """Язык текста: ``ru`` / ``en`` / ``mixed`` / ``unknown`` по счёту букв (§13.7).

    Та же логика, что в ``kg_extractors.query_parser`` (детект языка вопроса),
    здесь применённая к чанку/документу (§23.17: детект языка *источника*).
    """
    cyr = len(_CYR.findall(text))
    lat = len(_LAT.findall(text))
    if cyr == 0 and lat == 0:
        return "unknown"
    if cyr and lat and min(cyr, lat) / max(cyr, lat) > _MIXED_RATIO:
        return "mixed"
    return "ru" if cyr >= lat else "en"


def ocr_noise_score(text: str) -> dict[str, Any]:
    """Оценка «грязности» текста: доля homoglyph-битых слов и не-буквенного мусора.

    ``mixed_word_ratio`` — доля слов, где кириллица и латиница смешаны внутри
    одного токена (например ``никeль`` с латинской ``e``) — прямой признак OCR.
    ``junk_ratio`` — доля не-буквенно-цифровых символов (кроме пробелов/пунктуации),
    растущая на «мусорном» скане.
    """
    words = _WORD.findall(text)
    mixed = sum(1 for w in words if _MIXED_WORD.search(w))
    total_chars = len(text)
    allowed = ".,:;!?()-—«»\"'/%°±"
    junk = sum(1 for ch in text if not ch.isalnum() and not ch.isspace() and ch not in allowed)
    mixed_ratio = mixed / len(words) if words else 0.0
    junk_ratio = junk / total_chars if total_chars else 0.0
    return {
        "words": len(words),
        "mixed_script_words": mixed,
        "mixed_word_ratio": round(mixed_ratio, 3),
        "junk_ratio": round(junk_ratio, 3),
        "dirty": bool(words) and (mixed_ratio > 0.05 or junk_ratio > 0.08),
    }


# --------------------------------------------------------------------------- #
# Node-embedding matrix over the live graph (cross-lingual retrieval surface)  #
# --------------------------------------------------------------------------- #
# Поля узла, из которых собираем embeddable-текст (мультиязычная модель ест ru/en
# в одном пространстве, поэтому конкатенация ru-имени и en-описания — норм).
_TEXT_FIELDS = ("name", "canonical_name", "aliases_text", "text", "description")

# In-process кэш матрицы эмбеддингов узлов: db_path -> запись.
# Сигнатура = content-hash набора id (стабильна, не зависит от len), поэтому
# фоновый ingest, добавляющий/удаляющий узлы вне top-N, НЕ инвалидирует кэш и не
# триггерит пересчёт эмбеддингов на каждый вызов (H-3).
_MATRIX: dict[str, dict[str, Any]] = {}

# Верхний предел числа узлов, эмбеддящихся синхронно в реквесте. Полный граф
# (152k узлов) на CPU-Granite в запросе = hang/OOM/DoS, поэтому берём детермини-
# рованный top-N (ORDER BY id) — конфигурируемо через CROSSLINGUAL_NODE_LIMIT.
_NODE_LIMIT_DEFAULT = 2000

# WHERE-фильтр «эмбеддабельных» узлов — общий для загрузки и для дешёвого COUNT.
_NODE_WHERE = (
    "n.name IS NOT NULL OR n.text IS NOT NULL OR n.canonical_name IS NOT NULL"
)


def _node_limit() -> int:
    """Предел числа узлов для синхронного эмбеддинга (env CROSSLINGUAL_NODE_LIMIT)."""
    raw = os.getenv("CROSSLINGUAL_NODE_LIMIT")
    if raw:
        try:
            v = int(raw)
        except ValueError:
            return _NODE_LIMIT_DEFAULT
        if v > 0:
            return v
    return _NODE_LIMIT_DEFAULT


def _node_text(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for f in _TEXT_FIELDS:
        v = node.get(f)
        if v:
            s = str(v).strip()
            if s and s not in parts:
                parts.append(s)
    return " — ".join(parts)


def _load_nodes(store: Any, limit: int | None = None) -> list[dict[str, Any]]:
    """Детерминированный top-N эмбеддабельных узлов (ORDER BY id, LIMIT).

    Предел обязателен: без него /status и /search тянут весь граф (152k) и
    синхронно эмбеддят его Granite на CPU в реквесте → hang/OOM/DoS (H-3).
    ``ORDER BY n.id`` даёт стабильный набор, на котором content-hash кэша не
    «дёргается» от фонового ingest.
    """
    lim = _node_limit() if limit is None else limit
    rows = store.rows(
        f"MATCH (n:Node) WHERE {_NODE_WHERE} RETURN n ORDER BY n.id LIMIT $limit",
        {"limit": lim},
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        node = store._node_dict(row[0])
        nid = node.get("id")
        text = _node_text(node)
        if not nid or not text:
            continue
        out.append(
            {
                "id": nid,
                "name": node.get("name") or node.get("canonical_name") or nid,
                "label": node.get("label", "Node"),
                "domain": node.get("domain"),
                "text": text,
            }
        )
    return out


def _count_candidates(store: Any) -> int:
    """Дешёвый COUNT эмбеддабельных узлов (без эмбеддинга) — для /status (H-3)."""
    try:
        rows = store.rows(
            f"MATCH (n:Node) WHERE {_NODE_WHERE} RETURN count(n)",
            {},
        )
        return int(rows[0][0]) if rows else 0
    except (IndexError, TypeError, ValueError):
        return 0


def _signature(items: list[dict[str, Any]]) -> str:
    """Стабильный ключ кэша: content-hash упорядоченного набора id (не len).

    len(items) как сигнатура ломается на живом графе — фоновый ingest постоянно
    меняет счётчик, из-за чего кэш инвалидируется на каждый вызов и весь top-N
    переэмбеддивается заново (H-3). Хэш от самих id стабилен, пока набор тот же.
    """
    h = hashlib.sha1()
    for it in items:
        h.update(str(it["id"]).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _matrix(store: Any) -> dict[str, Any]:
    key = getattr(store, "db_path", "default")
    items = _load_nodes(store)
    signature = _signature(items)
    cached = _MATRIX.get(key)
    if cached is not None and cached["signature"] == signature:
        return cached
    t0 = time.perf_counter()
    vectors = embed([it["text"] for it in items]) if items else []
    langs = [detect_language(it["text"]) for it in items]
    record = {
        "signature": signature,
        "count": len(items),
        "items": items,
        "vectors": vectors,
        "langs": langs,
    }
    _MATRIX[key] = record
    _log.info(
        "crosslingual.matrix_built",
        nodes=len(items),
        seconds=round(time.perf_counter() - t0, 2),
    )
    return record


def _snippet(text: str, limit: int = 220) -> str:
    t = " ".join(text.split())
    return t[:limit] + ("…" if len(t) > limit else "")


# --------------------------------------------------------------------------- #
# OCR-noise injector (deterministic, seeded) — «грязный» ru-текст              #
# --------------------------------------------------------------------------- #
# Визуально близкие кириллица→латиница (homoglyphs), типичные ошибки OCR.
_HOMOGLYPH: dict[str, str] = {
    "а": "a", "е": "e", "о": "o", "с": "c", "р": "p", "х": "x",
    "у": "y", "к": "k", "н": "h", "в": "b", "м": "m", "т": "t",
}


def inject_ocr_noise(text: str, level: float, seed: int) -> str:
    """Инъекция OCR-шума в ru-текст: homoglyph-подмены, дропы, дубли символов.

    ``level`` ∈ [0,1] — вероятность порчи каждого символа. Детерминировано по
    ``seed`` (воспроизводимость демо). Моделирует реальный «грязный» скан:
    кириллица подменяется латинским двойником, символы теряются/дублируются.
    """
    rng = random.Random(seed)
    out: list[str] = []
    for ch in text:
        r = rng.random()
        if r >= level:
            out.append(ch)
            continue
        low = ch.lower()
        pick = rng.random()
        if low in _HOMOGLYPH and pick < 0.6:  # homoglyph-подмена
            sub = _HOMOGLYPH[low]
            out.append(sub.upper() if ch.isupper() else sub)
        elif pick < 0.8:  # дроп символа
            continue
        else:  # дубль символа
            out.append(ch)
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------------------- #
# Bilingual parallel mini-corpus for the recall demo (mining / materials)      #
# --------------------------------------------------------------------------- #
# Каждая пара — один и тот же факт по-русски и по-английски. ru-запрос должен
# находить en-документ (cross-lingual), несмотря на OCR-шум в запросе.
_PAIRS: list[dict[str, str]] = [
    {
        "id": "flotation",
        "ru": "Флотация сульфидных медных руд с ксантогенатом в качестве собирателя",
        "en": "Froth flotation of sulfide copper ores using xanthate as the collector reagent",
    },
    {
        "id": "heap_leach",
        "ru": "Кучное выщелачивание окисленных медных руд серной кислотой",
        "en": "Heap leaching of oxidized copper ore with sulfuric acid solution",
    },
    {
        "id": "al_cu_aging",
        "ru": "Старение алюминиево-медного сплава повышает предел текучести за счёт выделений",
        "en": "Aging of an aluminum-copper alloy raises the yield strength through precipitation",
    },
    {
        "id": "sag_mill",
        "ru": "Полусамоизмельчение руды в мельнице ПСИ перед флотационным переделом",
        "en": "Semi-autogenous grinding of ore in a SAG mill ahead of the flotation circuit",
    },
    {
        "id": "cyanidation",
        "ru": "Цианирование золотосодержащей руды с последующей сорбцией на активированный уголь",
        "en": "Cyanidation of gold-bearing ore followed by carbon-in-pulp adsorption",
    },
    {
        "id": "tailings",
        "ru": "Складирование хвостов обогащения в хвостохранилище и риск фильтрации",
        "en": "Storage of processing tailings in a tailings dam and the seepage risk",
    },
    {
        "id": "smelting",
        "ru": "Пирометаллургическая плавка медного концентрата в печи взвешенной плавки",
        "en": "Pyrometallurgical smelting of copper concentrate in a flash smelting furnace",
    },
    {
        "id": "electrowinning",
        "ru": "Электроэкстракция меди из раствора после экстракции органическим реагентом",
        "en": "Copper electrowinning from solution after solvent extraction with organics",
    },
]

_DEMO_CACHE: dict[str, Any] = {}


def _demo_en_matrix() -> dict[str, Any]:
    """Кэшированные эмбеддинги en-стороны параллельного корпуса."""
    if "vectors" not in _DEMO_CACHE:
        en_texts = [p["en"] for p in _PAIRS]
        _DEMO_CACHE["vectors"] = embed(en_texts)
        _DEMO_CACHE["ids"] = [p["id"] for p in _PAIRS]
    return _DEMO_CACHE


def _rank_against(query_vec: list[float], vectors: list[list[float]], k: int) -> list[int]:
    scored = sorted(
        range(len(vectors)),
        key=lambda i: cosine(query_vec, vectors[i]),
        reverse=True,
    )
    return scored[:k]


# --------------------------------------------------------------------------- #
# Request models                                                               #
# --------------------------------------------------------------------------- #
class DetectRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=200)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(default=10, ge=1, le=50)
    # Опциональный фильтр: показать только хиты этого языка (для наглядности cross-lingual).
    only_lang: str | None = Field(default=None, description="ru|en|mixed — фильтр языка хитов")


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/status")
def status() -> dict:
    """Готовность cross-lingual поиска — ДЕШЁВО, без эмбеддинга графа (H-3).

    /status НЕ строит матрицу эмбеддингов (это тяжёлый CPU-путь на весь top-N).
    Готовность = мультиязычная модель + наличие эмбеддабельных узлов (дешёвый
    COUNT). Если матрица уже прогрета (после /search), отдаём её статистику из
    кэша, но никогда не пересчитываем её здесь.
    """
    store = get_store()
    settings = get_settings()
    is_multilingual = "multilingual" in settings.embedding_model.lower()
    key = getattr(store, "db_path", "default")
    cached = _MATRIX.get(key)

    result: dict[str, Any] = {
        "embedding_model": settings.embedding_model,
        "multilingual": is_multilingual,
        "node_limit": _node_limit(),
        "warm": cached is not None,
    }
    if cached is not None:
        by_lang: dict[str, int] = {}
        for lang in cached["langs"]:
            by_lang[lang] = by_lang.get(lang, 0) + 1
        result["available"] = is_multilingual and bool(cached["items"])
        result["nodes_indexed"] = cached["count"]
        result["nodes_by_language"] = by_lang
    else:
        candidates = _count_candidates(store)
        result["available"] = is_multilingual and candidates > 0
        result["nodes_indexed"] = 0
        result["candidate_nodes"] = candidates
        result["nodes_by_language"] = {}
    return result


@router.post("/detect")
def detect(req: DetectRequest) -> dict:
    """Детект языка (ru/en/mixed) + OCR-шум для каждого переданного текста/чанка."""
    results = []
    for text in req.texts:
        results.append(
            {
                "text": _snippet(text, 160),
                "language": detect_language(text),
                "noise": ocr_noise_score(text),
            }
        )
    counts: dict[str, int] = {}
    for r in results:
        counts[r["language"]] = counts.get(r["language"], 0) + 1
    return {"count": len(results), "by_language": counts, "results": results}


@router.post("/search")
def search(req: SearchRequest) -> dict:
    """Cross-lingual семантический поиск по узлам живого графа (§23.17/§4.4).

    Запрос эмбеддится мультиязычной моделью и сравнивается по косинусу с
    node-embedding'ами. ru-запрос находит en-узлы (и наоборот) — каждый хит
    помечен своим детектированным языком и признаком cross-lingual (язык хита ≠
    язык запроса).
    """
    t0 = time.perf_counter()
    store = get_store()
    matrix = _matrix(store)
    q_lang = detect_language(req.query)
    if not matrix["items"]:
        return {"query": req.query, "query_language": q_lang, "count": 0, "hits": []}

    q_vec = embed_one(req.query)
    items = matrix["items"]
    vectors = matrix["vectors"]
    langs = matrix["langs"]

    scored: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        hit_lang = langs[i]
        if req.only_lang and hit_lang != req.only_lang:
            continue
        is_cross = q_lang in ("ru", "en") and hit_lang in ("ru", "en") and hit_lang != q_lang
        scored.append(
            {
                "id": item["id"],
                "name": item["name"],
                "label": item["label"],
                "domain": item.get("domain"),
                "language": hit_lang,
                "cross_lingual": is_cross,
                "similarity": round(float(cosine(q_vec, vectors[i])), 4),
                "snippet": _snippet(item["text"]),
            }
        )
    scored.sort(key=lambda d: d["similarity"], reverse=True)
    hits = scored[: req.k]
    cross = sum(1 for h in hits if h["cross_lingual"])
    _log.info("crosslingual.search", q=req.query[:80], q_lang=q_lang, hits=len(hits), cross=cross)
    return {
        "query": req.query,
        "query_language": q_lang,
        "count": len(hits),
        "cross_lingual_hits": cross,
        "hits": hits,
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@router.get("/demo")
def demo(noise: float = 0.15, seed: int = 23) -> dict:
    """Recall на «грязном» ru-тексте с OCR-шумом (§23.17 критерий приёмки).

    Параллельный ru↔en мини-корпус (горное дело/материаловедение). Для каждого
    ru-запроса берём (а) чистый ru и (б) ru с инъекцией OCR-шума уровня ``noise``,
    эмбеддим мультиязычной моделью и ищем ближайший en-документ. Меряем
    recall@1/@3 попадания в правильный en-таргет (cross-lingual) для чистого и
    грязного ввода и показываем деградацию — прямое подтверждение, что ru-запрос
    находит en-контент даже под OCR-шумом.
    """
    if not 0.0 <= noise <= 0.9:
        raise HTTPException(status_code=400, detail="noise must be in [0.0, 0.9]")

    en = _demo_en_matrix()
    en_vecs = en["vectors"]
    en_ids = en["ids"]

    def _run(query_of: Any) -> dict[str, Any]:
        hit1 = hit3 = 0
        sims: list[float] = []
        per: list[dict[str, Any]] = []
        for idx, pair in enumerate(_PAIRS):
            q = query_of(pair, idx)
            q_vec = embed_one(q)
            top = _rank_against(q_vec, en_vecs, 3)
            top_ids = [en_ids[j] for j in top]
            r1 = top_ids[0] == pair["id"]
            r3 = pair["id"] in top_ids
            sim = float(cosine(q_vec, en_vecs[idx]))
            hit1 += int(r1)
            hit3 += int(r3)
            sims.append(sim)
            per.append(
                {
                    "id": pair["id"],
                    "query": q,
                    "query_language": detect_language(q),
                    "noise": ocr_noise_score(q),
                    "target_en": pair["en"],
                    "found_top1": top_ids[0],
                    "hit@1": r1,
                    "hit@3": r3,
                    "similarity_to_target": round(sim, 4),
                }
            )
        n = len(_PAIRS)
        return {
            "recall_at_1": round(hit1 / n, 3),
            "recall_at_3": round(hit3 / n, 3),
            "mean_similarity": round(sum(sims) / n, 4),
            "cases": per,
        }

    clean = _run(lambda pair, idx: pair["ru"])
    dirty = _run(lambda pair, idx: inject_ocr_noise(pair["ru"], noise, seed + idx))

    return {
        "pairs": len(_PAIRS),
        "noise_level": noise,
        "seed": seed,
        "embedding_model": get_settings().embedding_model,
        "direction": "ru query → en document (cross-lingual)",
        "clean": clean,
        "dirty": dirty,
        "degradation": {
            "recall_at_1": round(clean["recall_at_1"] - dirty["recall_at_1"], 3),
            "recall_at_3": round(clean["recall_at_3"] - dirty["recall_at_3"], 3),
            "mean_similarity": round(clean["mean_similarity"] - dirty["mean_similarity"], 4),
        },
    }
