"""«Похожие материалы/режимы» — vector-search по node-embeddings (§3.13, §8.4).

§3.13 фиксирует векторный поиск ближайших сущностей по эмбеддингам узлов
(``db.index.vector.queryNodes('entity_embedding_index', $k, $vec)`` /
:class:`~kg_retrievers.entity_index.EntityVectorIndex` над Qdrant), но во фронте он
не выведен ни разу (0 упоминаний «similar»). Этот роутер закрывает пробел: по
одному клику из карточки сущности или свободного запроса он находит семантические
аналоги — «найди сплавы/режимы, похожие на этот», — ранжируя по косинусной близости
node-embedding'ов.

Отличие от соседних «similar»-ручек — метрика:

* ``/gds-live/similar`` и ``/similarity-links`` — *топологическое* сходство
  (Jaccard общих соседей, ``gds.nodeSimilarity``): похожи те, кто делит соседей в
  графе;
* ``/similar-materials`` — *фасетное* сходство (общие режимы/свойства);
* **этот роутер** — *семантическое* сходство по эмбеддингам (§3.13): близкими
  оказываются сущности со схожим описанием/названием/синонимами, даже если в графе
  они ещё никак не связаны. Это и есть «vector-search по node embeddings».

Два пути расчёта, один контракт (поле ``method`` возвращается честно):

* **entity_index** — если Qdrant-коллекция ``kg_entities`` уже наполнена
  (:class:`EntityVectorIndex`, §4.5), переиспользуем её ``similar_entities`` —
  быстрый персистентный ANN-поиск по заранее записанным node-embedding'ам.
* **on_the_fly** — иначе считаем эмбеддинги сущностных узлов (метки §3.4
  ``ENTITY_LABELS``) той же моделью (``kg_retrievers.embeddings``) и тем же
  текстом-описанием (``entity_index._entity_text``), кэшируем в процессе и берём
  top-k по косинусу (``kg_schema.vector_index_spec.cosine``). Сущностных узлов
  немного (сотни), поэтому полный перебор дёшев и не требует GDS/vector-index на
  живом Neo4j — фича работает на server-профиле как есть.

Роутер только читает — граф/индексы не меняет. Префикс ``/similar-embeddings`` не
конфликтует с топологическим ``/similarity-links`` и фасетным ``/similar-materials``.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import get_logger
from kg_retrievers.embeddings import embed, embed_one
from kg_retrievers.entity_index import _entity_text
from kg_schema.labels import ENTITY_LABELS
from kg_schema.vector_index_spec import cosine

router = APIRouter(prefix="/api/v1/similar-embeddings", tags=["similar-embeddings"])

_log = get_logger("api.similar_embeddings")

# Сущностные метки (§3.4) — только они несут осмысленный embeddable-текст.
_ENTITY_LABELS: list[str] = sorted(str(label) for label in ENTITY_LABELS)

# Приоритет меток для дефолтных seed'ов (материалы/режимы — «герои» фичи).
_SEED_PRIORITY: dict[str, int] = {
    "Material": 0,
    "Alloy": 1,
    "ProcessingRegime": 2,
    "TechnologySolution": 3,
    "Property": 4,
    "Method": 5,
    "Equipment": 6,
    "ChemicalElement": 7,
}

# Человеко-читаемые подписи меток для reason-строки.
_LABEL_RU: dict[str, str] = {
    "Material": "материал",
    "Alloy": "сплав",
    "ProcessingRegime": "режим обработки",
    "TechnologySolution": "технологическое решение",
    "Property": "свойство",
    "Method": "метод",
    "Equipment": "оборудование",
    "ChemicalElement": "химический элемент",
    "Facility": "объект",
    "Lab": "лаборатория",
    "Person": "исследователь",
    "Geography": "география",
    "Recommendation": "рекомендация",
    "ResearchTeam": "коллектив",
}

# In-process кэш матрицы эмбеддингов сущностей: db_path -> запись.
# Пересобирается при изменении числа сущностных узлов (дешёвая сигнатура).
_MATRIX: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------- #
# On-the-fly node-embedding matrix (§3.13 fallback path, работает на любом store)
# --------------------------------------------------------------------------- #
def _load_entities(store: Any) -> list[dict[str, Any]]:
    """Сущностные узлы с embeddable-текстом (id, name, label, text)."""
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels "
        "AND (n.name IS NOT NULL OR n.aliases_text IS NOT NULL) RETURN n",
        {"labels": _ENTITY_LABELS},
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        node = store._node_dict(row[0])
        nid = node.get("id")
        text = _entity_text(node)
        if not nid or not text:
            continue
        out.append(
            {
                "id": nid,
                "name": node.get("name") or node.get("canonical_name") or nid,
                "label": node.get("label", "Entity"),
                "text": text,
            }
        )
    return out


def _matrix(store: Any) -> dict[str, Any]:
    """Кэшированная матрица (ids/names/labels/vectors) node-embedding'ов сущностей."""
    key = getattr(store, "db_path", "default")
    items = _load_entities(store)
    signature = len(items)
    cached = _MATRIX.get(key)
    if cached is not None and cached["signature"] == signature:
        return cached

    t0 = time.perf_counter()
    vectors = embed([it["text"] for it in items]) if items else []
    record = {
        "signature": signature,
        "ids": [it["id"] for it in items],
        "names": [it["name"] for it in items],
        "labels": [it["label"] for it in items],
        "vectors": vectors,
        "index": {it["id"]: i for i, it in enumerate(items)},
    }
    _MATRIX[key] = record
    _log.info(
        "similar_embeddings.matrix_built",
        entities=signature,
        seconds=round(time.perf_counter() - t0, 2),
    )
    return record


def _rank(
    query_vec: list[float],
    matrix: dict[str, Any],
    k: int,
    label_filter: set[str] | None,
    exclude_id: str | None,
) -> list[dict[str, Any]]:
    """Top-k сущностей по косинусной близости к ``query_vec`` (§3.13)."""
    ids = matrix["ids"]
    names = matrix["names"]
    labels = matrix["labels"]
    vectors = matrix["vectors"]
    scored: list[dict[str, Any]] = []
    for i, vec in enumerate(vectors):
        if exclude_id is not None and ids[i] == exclude_id:
            continue
        if label_filter and labels[i] not in label_filter:
            continue
        scored.append(
            {
                "id": ids[i],
                "name": names[i],
                "label": labels[i],
                "similarity": round(float(cosine(query_vec, vec)), 4),
            }
        )
    scored.sort(key=lambda d: d["similarity"], reverse=True)
    return scored[: max(1, k)]


# --------------------------------------------------------------------------- #
# Qdrant entity-index path (§4.5) — persistent ANN when the collection is filled
# --------------------------------------------------------------------------- #
def _entity_index() -> Any | None:
    """Наполненный :class:`EntityVectorIndex` (или ``None``, если пуст/недоступен)."""
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        idx = EntityVectorIndex()
        if idx.count() > 0:
            return idx
    except Exception as exc:  # qdrant заблокирован / коллекции нет
        _log.warning("similar_embeddings.entity_index_unavailable", error=str(exc)[:200])
    return None


def _reason(label: str, score: float) -> str:
    """Короткое объяснение: почему сущность в выдаче (семантика + сила)."""
    ru = _LABEL_RU.get(label, label.lower())
    strength = "очень близко" if score >= 0.8 else ("близко" if score >= 0.6 else "родственно")
    return f"{ru} · {strength} по эмбеддингу (cos={score:.2f})"


def _decorate(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for h in hits:
        h["reason"] = _reason(h.get("label", "Entity"), float(h.get("similarity", 0.0)))
    return hits


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/status")
def status() -> dict:
    """Доступность семантического поиска: наличие индекса/сущностей и метод."""
    store = get_store()
    idx = _entity_index()
    if idx is not None:
        return {"available": True, "method": "entity_index", "entities": idx.count()}
    matrix = _matrix(store)
    return {
        "available": bool(matrix["ids"]),
        "method": "on_the_fly",
        "entities": len(matrix["ids"]),
        "labels": sorted(set(matrix["labels"])),
    }


@router.get("/seeds")
def seeds(
    label: str | None = Query(None, description="фильтр метки сущности (напр. Material)"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """Сущности-кандидаты для выбора seed'а (материалы/режимы первыми)."""
    store = get_store()
    matrix = _matrix(store)
    wanted = label if label in _ENTITY_LABELS else None
    rows: list[dict[str, Any]] = []
    for i, nid in enumerate(matrix["ids"]):
        lab = matrix["labels"][i]
        if wanted and lab != wanted:
            continue
        rows.append({"id": nid, "name": matrix["names"][i], "label": lab})
    rows.sort(key=lambda d: (_SEED_PRIORITY.get(d["label"], 99), d["name"].lower()))
    return {
        "count": len(rows[:limit]),
        "labels": sorted(set(matrix["labels"])),
        "seeds": rows[:limit],
    }


@router.get("/similar")
def similar(
    seed: str = Query(..., description="id сущности-источника (материал/режим/…)"),
    k: int = Query(10, ge=1, le=50, description="сколько аналогов вернуть"),
    labels: str | None = Query(
        None, description="csv меток для фильтра выдачи (по умолчанию — все)"
    ),
    same_label: bool = Query(
        False, description="искать аналоги только той же метки, что и seed"
    ),
) -> dict:
    """Семантические аналоги ``seed`` по node-embedding'ам (§3.13, one-click «похожие»).

    Возвращает top-k ближайших по косинусу сущностей (сам seed исключён —
    self-nearest гарантирован конструкцией), с оценкой близости и объяснением.
    """
    store = get_store()
    node = store.get_node(seed)
    if node is None:
        raise HTTPException(status_code=404, detail="seed entity not found")

    seed_label = node.get("label")
    label_filter: set[str] | None = None
    if same_label and seed_label:
        label_filter = {seed_label}
    elif labels:
        picked = {x.strip() for x in labels.split(",") if x.strip() in _ENTITY_LABELS}
        label_filter = picked or None

    idx = _entity_index()
    if idx is not None:
        raw = idx.similar_entities(seed, k=k * 3 if label_filter else k)
        hits = [
            {"id": h.id, "name": h.name, "label": h.label, "similarity": round(float(h.score), 4)}
            for h in raw
            if not label_filter or h.label in label_filter
        ][:k]
        method = "entity_index"
    else:
        matrix = _matrix(store)
        pos = matrix["index"].get(seed)
        if pos is None:
            return {
                "seed": {"id": seed, "name": node.get("name") or seed, "label": seed_label},
                "method": "on_the_fly",
                "count": 0,
                "similar": [],
                "note": "у сущности нет названия/синонимов для эмбеддинга — сравнить не с чем",
            }
        hits = _rank(matrix["vectors"][pos], matrix, k, label_filter, exclude_id=seed)
        method = "on_the_fly"

    _decorate(hits)
    _log.info("similar_embeddings.similar", seed=seed, method=method, returned=len(hits))
    return {
        "seed": {"id": seed, "name": node.get("name") or seed, "label": seed_label},
        "method": method,
        "count": len(hits),
        "similar": hits,
    }


@router.get("/by-text")
def by_text(
    q: str = Query(..., min_length=1, description="свободный запрос (для Ask)"),
    k: int = Query(10, ge=1, le=50),
    labels: str | None = Query(None, description="csv меток для фильтра выдачи"),
) -> dict:
    """Семантический поиск сущностей по свободному тексту — «аналоги» из запроса (Ask).

    Эмбеддит запрос той же моделью и возвращает ближайшие сущности графа —
    мостик от формулировки пользователя к материалам/режимам корпуса (§3.13/§4.5).
    """
    store = get_store()
    label_filter: set[str] | None = None
    if labels:
        picked = {x.strip() for x in labels.split(",") if x.strip() in _ENTITY_LABELS}
        label_filter = picked or None

    idx = _entity_index()
    if idx is not None:
        raw = idx.similar_entities(q, k=k * 3 if label_filter else k)
        hits = [
            {"id": h.id, "name": h.name, "label": h.label, "similarity": round(float(h.score), 4)}
            for h in raw
            if not label_filter or h.label in label_filter
        ][:k]
        method = "entity_index"
    else:
        matrix = _matrix(store)
        if not matrix["ids"]:
            return {"query": q, "method": "on_the_fly", "count": 0, "similar": []}
        hits = _rank(embed_one(q), matrix, k, label_filter, exclude_id=None)
        method = "on_the_fly"

    _decorate(hits)
    _log.info("similar_embeddings.by_text", q=q[:80], method=method, returned=len(hits))
    return {"query": q, "method": method, "count": len(hits), "similar": hits}
