"""§4.5 named ``ScoredChunk`` return type for the dense/keyword search stores.

Единый возвращаемый тип для гибридного поиска (§4.5): и
:class:`~kg_retrievers.qdrant_server_store.QdrantServerStore` (dense/Cosine), и
:class:`~kg_retrievers.opensearch_store.OpenSearchKeywordStore` (BM25) отдают
«сырые» ``dict`` вида ``{id, text, score, doc_id, page}`` — этот модуль поднимает
их до одного frozen dataclass с явным ``source`` и удобной проекцией в ``dict``.

Маперы :meth:`ScoredChunk.from_qdrant_hit` / :meth:`ScoredChunk.from_opensearch_hit`
переносят поля один-в-один и проставляют канал (``qdrant`` / ``opensearch``);
недостающие опциональные поля (``doc_id``/``page``/``material_ids``) получают
дефолты. :func:`merge_scored` сливает два ранжированных списка через Reciprocal
Rank Fusion (§7.5 Node 6, §12.4): ``score = Σ 1/(k+rank)`` по обоим спискам, так
что документ, встретившийся в обоих каналах, получает более высокий fused-score.

Pure python — no store/graph/DB access: на вход уже прочитанные hit-``dict``.
Kuzu note: custom node props are NOT queryable columns — retrievers RETURN base
columns and read the rest via ``get_node`` before assembling these hit dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

# §4.5 канал источника — фиксируется в ScoredChunk.source мапером.
SOURCE_QDRANT = "qdrant"
SOURCE_OPENSEARCH = "opensearch"

# Reciprocal Rank Fusion константа по умолчанию (§12.4, config ``rrf_k``).
DEFAULT_RRF_K: int = 60


@dataclass(frozen=True)
class ScoredChunk:
    """One scored passage from a search backend (§4.5).

    ``id``/``text``/``score`` — обязательны; ``doc_id``/``page``/``material_ids``
    опциональны (дефолты ``None``/``None``/``()``); ``source`` — канал происхождения
    (``qdrant``/``opensearch``, пусто если не проставлен). ``material_ids`` хранится
    как ``tuple`` — dataclass остаётся неизменяемым и хешируемым.
    """

    id: str
    text: str
    score: float
    doc_id: str | None = None
    page: int | None = None
    material_ids: tuple[str, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        # Нормализуем любую итерируемую коллекцию material_ids к tuple (immutability).
        if not isinstance(self.material_ids, tuple):
            object.__setattr__(self, "material_ids", tuple(self.material_ids))

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection; ``material_ids`` — список для сериализации (§4.5)."""
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "doc_id": self.doc_id,
            "page": self.page,
            "material_ids": list(self.material_ids),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScoredChunk:
        """Rebuild from an :meth:`as_dict` projection; optional fields default (§4.5)."""
        return cls(
            id=d.get("id", ""),
            text=d.get("text", ""),
            score=float(d.get("score", 0.0)),
            doc_id=d.get("doc_id"),
            page=d.get("page"),
            material_ids=tuple(d.get("material_ids") or ()),
            source=d.get("source", ""),
        )

    @classmethod
    def from_qdrant_hit(cls, d: dict[str, Any]) -> ScoredChunk:
        """Map a :meth:`QdrantServerStore.search` hit ``{id,text,score,doc_id,page}`` (§4.5).

        ``material_ids`` в поисковом ответе отсутствует, поэтому берётся из ``dict``
        только если передан явно, иначе — пустой tuple; ``source`` = ``qdrant``.
        """
        return _from_hit(d, SOURCE_QDRANT)

    @classmethod
    def from_opensearch_hit(cls, d: dict[str, Any]) -> ScoredChunk:
        """Map an OpenSearch search hit (same shape); ``source`` = ``opensearch`` (§4.5)."""
        return _from_hit(d, SOURCE_OPENSEARCH)


def _from_hit(d: dict[str, Any], source: str) -> ScoredChunk:
    """Shared hit-``dict`` → :class:`ScoredChunk` mapping with a fixed ``source`` (§4.5)."""
    return ScoredChunk(
        id=d.get("id", ""),
        text=d.get("text", ""),
        score=float(d.get("score", 0.0)),
        doc_id=d.get("doc_id"),
        page=d.get("page"),
        material_ids=tuple(d.get("material_ids") or ()),
        source=source,
    )


def merge_scored(
    a: list[ScoredChunk],
    b: list[ScoredChunk],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[ScoredChunk]:
    """Reciprocal-rank merge of two ranked :class:`ScoredChunk` lists (§7.5 Node 6, §12.4).

    Каждому id начисляется ``1/(k+rank)`` (rank 1-based, лучший = 1) из каждого
    списка, где он встречается; итоговый fused ``score`` — сумма вкладов, так что
    документ из обоих каналов получает более высокий fused-score и всплывает выше.
    При совпадении id метаданные берутся у представителя с бóльшим исходным
    ``score`` (ties → первый по порядку появления). Пустой вход → ``[]``.
    """
    if k <= 0:
        raise ValueError(f"rrf k must be positive, got {k!r}")
    contrib: dict[str, float] = {}
    rep: dict[str, ScoredChunk] = {}
    order: list[str] = []
    for chunks in (a, b):
        for position, chunk in enumerate(chunks):
            rr = 1.0 / (k + position + 1)  # 1-based rank → 1/(k+rank)
            if chunk.id not in contrib:
                contrib[chunk.id] = rr
                rep[chunk.id] = chunk
                order.append(chunk.id)
            else:
                contrib[chunk.id] += rr
                if chunk.score > rep[chunk.id].score:  # keep higher-scored representative
                    rep[chunk.id] = chunk
    fused = [replace(rep[cid], score=contrib[cid]) for cid in order]
    # Stable sort: равные fused-score сохраняют порядок первого появления.
    fused.sort(key=lambda c: c.score, reverse=True)
    return fused
