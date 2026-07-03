"""LightRAG dual-level keyword retrieval over the Kuzu graph (§11.12 / §12).

Реализация двухуровневого поиска по ключевым словам из статьи **LightRAG**
(«LightRAG: Simple and Fast Retrieval-Augmented Generation», HKUDS,
arXiv:2410.05779, MIT license — https://github.com/HKUDS/LightRAG). LightRAG
раскладывает запрос на два набора ключей и ведёт по ним два независимых обхода:

* **low-level keys** — конкретные сущности / именные токены (specific entities):
  ведут точечный поиск по *именам* узлов графа (entity-name lookup) через
  переиспользуемый :class:`~kg_retrievers.entity_fulltext.EntityFulltext`;
* **high-level keys** — широкие тематические токены (broad themes / domains):
  ведут широкий скан по базовым колонкам ``label`` / ``domain`` узлов
  (broad label/domain scan).

Оба канала сливаются по **Reciprocal Rank Fusion** (переиспользуется
:func:`kg_retrievers.fusion.rrf_fuse`, §12.4), что даёт единый дедуплицированный
ранжированный список (dual-level retrieval из статьи).

Kuzu note (§3): пользовательские свойства узла НЕ являются queryable-колонками —
здесь читаются только базовые колонки (``id`` / ``name`` / ``canonical_name`` /
``aliases_text`` / ``label`` / ``domain``), а обогащение слитых хитов идёт через
:meth:`~kg_retrievers.graph_store.KuzuGraphStore.get_node`. Модуль не пишет в граф.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kg_common import canonical_key
from kg_retrievers.entity_fulltext import EntityFulltext
from kg_retrievers.fusion import DEFAULT_RRF_K, rrf_fuse

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping, Sequence

    from kg_retrievers.graph_store import KuzuGraphStore

# Минимальная длина значимого токена (после фолдинга) — короче отбрасываем.
_MIN_TOKEN: int = 2

# Служебные слова RU/EN — не несут смысла для поиска и в ключи не попадают (§11.12).
_STOPWORDS: frozenset[str] = frozenset(
    {
        # EN
        "the",
        "a",
        "an",
        "of",
        "for",
        "and",
        "or",
        "to",
        "in",
        "on",
        "with",
        "by",
        "is",
        "are",
        "at",
        "as",
        "from",
        "into",
        "over",
        "under",
        "vs",
        "this",
        "that",
        "it",
        "be",
        "we",
        "you",
        # RU
        "и",
        "в",
        "на",
        "с",
        "по",
        "для",
        "из",
        "к",
        "о",
        "об",
        "от",
        "до",
        "за",
        "у",
        "не",
        "а",
        "или",
        "что",
        "как",
        "это",
        "при",
        "же",
        "бы",
    }
)

# Широкие тематические / доменные токены (high-level). Совпадение токена с этим
# словарём — сигнал «это тема/домен», а не конкретная сущность. RU/EN, folded.
_THEME_WORDS: frozenset[str] = frozenset(
    {
        # EN — broad concepts / domains / categories
        "technology",
        "technologies",
        "method",
        "methods",
        "methodology",
        "material",
        "materials",
        "process",
        "processes",
        "system",
        "systems",
        "approach",
        "approaches",
        "framework",
        "strategy",
        "treatment",
        "purification",
        "management",
        "application",
        "applications",
        "solution",
        "solutions",
        "comparison",
        "overview",
        "efficiency",
        "performance",
        "sustainability",
        "environmental",
        "industry",
        "industrial",
        "economics",
        "economic",
        "safety",
        "quality",
        "metallurgy",
        "chemistry",
        "domain",
        "field",
        "area",
        "concept",
        "theme",
        "recommendation",
        "standard",
        "technique",
        "techniques",
        # RU — широкие концепты / домены / категории
        "технология",
        "технологии",
        "метод",
        "методы",
        "методика",
        "материал",
        "материалы",
        "процесс",
        "процессы",
        "система",
        "системы",
        "подход",
        "подходы",
        "стратегия",
        "очистка",
        "управление",
        "применение",
        "решение",
        "решения",
        "сравнение",
        "обзор",
        "эффективность",
        "устойчивость",
        "промышленность",
        "экономика",
        "безопасность",
        "качество",
        "металлургия",
        "химия",
        "область",
        "направление",
        "концепция",
        "тема",
        "рекомендация",
        "стандарт",
    }
)

# Каналы RRF-слияния (§12.4): порядок фиксирован — сначала low, затем high.
_LOW_CHANNEL: str = "low"
_HIGH_CHANNEL: str = "high"


@dataclass(frozen=True)
class DualKeywords:
    """Двухуровневый разбор запроса: low-level сущности vs high-level темы (§11.12)."""

    low_level: tuple[str, ...]
    high_level: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        """Plain-dict проекция для UI/debug (§11.12)."""
        return {
            "low_level": list(self.low_level),
            "high_level": list(self.high_level),
        }


@dataclass(frozen=True)
class DualHit:
    """Один хит одного из каналов dual-level поиска (§11.12)."""

    id: str
    name: str  # отображаемое имя узла (name / canonical_name / id)
    label: str  # тип / категория узла (Kuzu base-col ``label``)
    matched: str  # ключевое слово канала, породившее хит
    score: float  # native-скор канала (fulltext для low, 1.0-маркер для high)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "matched": self.matched,
            "score": self.score,
        }


@dataclass(frozen=True)
class MergedHit:
    """Один слитый по RRF кандидат: id + rrf-score + вклад каналов (§12.4)."""

    id: str
    name: str
    score: float  # Reciprocal Rank Fusion score (Σ 1/(k+rank) по каналам)
    channels: tuple[str, ...]  # какие каналы (low/high) внесли вклад

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "channels": list(self.channels),
        }


@dataclass(frozen=True)
class DualResult:
    """Итог dual-level поиска: оба набора хитов + их RRF-слияние (§11.12)."""

    low_hits: tuple[DualHit, ...]
    high_hits: tuple[DualHit, ...]
    merged: tuple[MergedHit, ...]

    def as_dict(self) -> dict[str, list[dict[str, object]]]:
        """Plain-dict проекция для UI/debug explainability (§11.12)."""
        return {
            "low_hits": [h.as_dict() for h in self.low_hits],
            "high_hits": [h.as_dict() for h in self.high_hits],
            "merged": [h.as_dict() for h in self.merged],
        }


def extract_keywords(query: str) -> DualKeywords:
    """Разложить запрос на low-level (сущности) и high-level (темы) ключи (§11.12).

    LightRAG (arXiv:2410.05779) извлекает два набора ключевых слов. Здесь — без
    LLM, оффлайн-эвристикой: запрос фолдится (:func:`kg_common.canonical_key` —
    NFKC + lower), режется на токены; служебные слова и слишком короткие токены
    отбрасываются. Токен из :data:`_THEME_WORDS` идёт в high-level (широкая тема),
    остальные значимые токены — в low-level (конкретная сущность). Оба списка
    дедуплицируются с сохранением порядка; регистр уже приведён к нижнему.

    Пустой / пробельный / состоящий только из стоп-слов запрос → пустые списки.
    """
    if not query or not query.strip():
        return DualKeywords((), ())
    low: list[str] = []
    high: list[str] = []
    for tok in canonical_key(query).split():
        if len(tok) < _MIN_TOKEN or tok in _STOPWORDS:
            continue
        bucket = high if tok in _THEME_WORDS else low
        if tok not in bucket:
            bucket.append(tok)
    return DualKeywords(tuple(low), tuple(high))


def dual_retrieve(store: KuzuGraphStore, query: str, *, top_k: int = 8) -> DualResult:
    """Двухуровневый поиск LightRAG над :class:`KuzuGraphStore` (§11.12 / §12).

    Шаги (по статье arXiv:2410.05779):

    1. :func:`extract_keywords` — разбор запроса на low/high ключи;
    2. low-level ключи ведут entity-name lookup по именам узлов (fulltext);
    3. high-level ключи ведут broad label/domain scan по базовым колонкам;
    4. каналы сливаются по RRF (:func:`kg_retrievers.fusion.rrf_fuse`), слитые
       хиты обогащаются именем через ``store.get_node`` (Kuzu base-cols + get_node).

    ``top_k`` ограничивает каждый канал и итоговое слияние. Пустой запрос (или
    запрос без значимых ключей) → все три набора пусты (graceful).
    """
    keys = extract_keywords(query)
    nodes = _load_nodes(store)
    low_hits = _low_level_retrieve(nodes, keys.low_level, top_k)
    high_hits = _high_level_retrieve(nodes, keys.high_level, top_k)
    merged = _merge_rrf(store, low_hits, high_hits, top_k)
    return DualResult(tuple(low_hits), tuple(high_hits), tuple(merged))


def _load_nodes(store: KuzuGraphStore) -> list[dict[str, object]]:
    """Считать все узлы как base-col dicts (§3): ``RETURN n`` + ``_node_dict``."""
    rows = store.rows("MATCH (n:Node) RETURN n")
    return [store._node_dict(r[0]) for r in rows]


def _low_level_retrieve(
    nodes: Sequence[Mapping[str, object]],
    keys: Sequence[str],
    top_k: int,
) -> list[DualHit]:
    """Entity-name lookup: каждый low-level ключ ищется по именам узлов (§11.12).

    Переиспользует declension-tolerant :class:`EntityFulltext`. Для узла берётся
    лучший скор среди всех low-ключей; результат сортируется desc по скору, затем
    по id (стабильно), и режется до ``top_k``.
    """
    if not keys:
        return []
    index = EntityFulltext.build_from_nodes(nodes)
    best: dict[str, tuple[float, str, str, str]] = {}  # id -> (score, key, name, type)
    for key in keys:
        for hit in index.search(key, limit=top_k):
            prev = best.get(hit.id)
            if prev is None or hit.score > prev[0]:
                best[hit.id] = (hit.score, key, hit.label, hit.type)
    ordered = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return [
        DualHit(id=nid, name=meta[2], label=meta[3], matched=meta[1], score=meta[0])
        for nid, meta in ordered[:top_k]
    ]


def _high_level_retrieve(
    nodes: Sequence[Mapping[str, object]],
    keys: Sequence[str],
    top_k: int,
) -> list[DualHit]:
    """Broad label/domain scan: high-level ключи матчатся по ``label``/``domain``.

    Скан идёт по базовым (queryable) колонкам ``label`` и ``domain`` каждого узла
    (Kuzu note §3). Совпадение — подстрока folded-ключа в lower(label)/lower(domain).
    Порядок хитов: по порядку ключей, затем по id (стабильно, дедуп по id).
    """
    if not keys:
        return []
    seen: dict[str, DualHit] = {}
    for key in keys:
        matched = [nd for nd in nodes if _label_domain_match(nd, key)]
        for nd in sorted(matched, key=lambda n: str(n.get("id") or "")):
            nid = str(nd.get("id") or "")
            if not nid or nid in seen:
                continue
            name = nd.get("name") or nd.get("canonical_name") or nid
            seen[nid] = DualHit(
                id=nid,
                name=str(name),
                label=str(nd.get("label") or "Node"),
                matched=key,
                score=1.0,
            )
    return list(seen.values())[:top_k]


def _label_domain_match(node: Mapping[str, object], key: str) -> bool:
    """True если folded-ключ — подстрока базовой колонки ``label`` или ``domain``."""
    label = str(node.get("label") or "").lower()
    domain = str(node.get("domain") or "").lower()
    return key in label or key in domain


def _merge_rrf(
    store: KuzuGraphStore,
    low_hits: Sequence[DualHit],
    high_hits: Sequence[DualHit],
    top_k: int,
) -> list[MergedHit]:
    """Слить каналы low/high по Reciprocal Rank Fusion (§12.4), дедуп по id.

    Ранжирования каналов передаются в :func:`kg_retrievers.fusion.rrf_fuse`
    (``score = Σ 1/(k+rank)``). Слитые id обогащаются именем через ``get_node``
    (Kuzu base-cols + get_node), fallback — имя из канального хита или сам id.
    """
    rankings: dict[str, list[str]] = {
        _LOW_CHANNEL: [h.id for h in low_hits],
        _HIGH_CHANNEL: [h.id for h in high_hits],
    }
    fused = rrf_fuse(rankings, k=DEFAULT_RRF_K)
    name_by_id = {h.id: h.name for h in (*high_hits, *low_hits)}
    merged: list[MergedHit] = []
    for nid, score in fused[:top_k]:
        node = store.get_node(nid)
        name = (node or {}).get("name") or name_by_id.get(nid) or nid
        channels = tuple(ch for ch, ids in rankings.items() if nid in ids)
        merged.append(MergedHit(id=nid, name=str(name), score=score, channels=channels))
    return merged
