"""Spec §12.4: per-source weighted Reciprocal Rank Fusion (Weighted RRF).

Дополняет :func:`kg_retrievers.fusion.rrf_fuse` (невзвешенный) и
:mod:`kg_retrievers.rrf_tuning` (грид-серч только по ``k``): здесь каждый
источник получает СВОЙ вес, а не единый вклад ``1/(k+rank)``.

Формула §12.4 (0-indexed rank, лучший = rank 0)::

    score(doc) = Σ_source  weight_source / (k + rank_source(doc))

- Источник, отсутствующий в ``weights``, берётся с весом ``1.0`` (default).
- Вес ``0.0`` полностью убирает вклад источника (в ``contributions`` его нет).
- Сортировка: по ``score`` убыв.; ties — по ``doc_id`` (лексикографически).

Pure python — no store/graph access; caller собирает ``rankings``.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before assembling the rankings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# §12.4 RRF-константа по умолчанию (сглаживает разрыв между верхними рангами).
DEFAULT_RRF_K: int = 60

# Вес источника по умолчанию, если он не указан в ``weights`` (§12.4).
DEFAULT_SOURCE_WEIGHT: float = 1.0


@dataclass(frozen=True)
class WRRFHit:
    """Один документ после взвешенной RRF: ``score`` + вклад каждого источника.

    ``contributions`` — ``{source: weight_source / (k + rank)}``; источники с
    нулевым весом (или отсутствующие) в словарь не попадают. Сумма всех
    значений ``contributions`` равна ``score`` (explainability, §12.4).
    """

    doc_id: str
    score: float
    contributions: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Plain-dict проекция для UI/debug (per-source вклад суммируется в score)."""
        return {
            "doc_id": self.doc_id,
            "score": self.score,
            "contributions": dict(self.contributions),
        }


def weighted_rrf_fuse(
    rankings: dict[str, list[str]],
    weights: dict[str, float] | None = None,
    k: int = DEFAULT_RRF_K,
) -> list[WRRFHit]:
    """Per-source weighted Reciprocal Rank Fusion (§12.4).

    ``rankings`` maps a source name to an ordered ``doc_id`` list (лучший —
    первым, rank 0-indexed). ``weights`` задаёт вес источника; отсутствующий
    источник берётся с ``DEFAULT_SOURCE_WEIGHT`` (1.0), вес ``0.0`` убирает
    вклад источника целиком. ``score = Σ_source weight/(k+rank)``; результат
    отсортирован по ``score`` убыв., ties — по ``doc_id``. Пусто → ``[]``.
    """
    if k <= 0:
        raise ValueError(f"rrf k must be positive, got {k!r}")
    weights = weights or {}
    scores: dict[str, float] = {}
    contributions: dict[str, dict[str, float]] = {}
    for source, doc_ids in rankings.items():
        weight = float(weights.get(source, DEFAULT_SOURCE_WEIGHT))
        if weight == 0.0:
            continue  # Нулевой вес — источник не вносит вклада (§12.4).
        for rank, doc_id in enumerate(doc_ids):  # rank 0-indexed
            contribution = weight / (k + rank)
            scores[doc_id] = scores.get(doc_id, 0.0) + contribution
            contributions.setdefault(doc_id, {})[source] = contribution
    hits = [
        WRRFHit(doc_id=doc_id, score=scores[doc_id], contributions=contributions[doc_id])
        for doc_id in scores
    ]
    # Сортировка: score убыв., затем doc_id (детерминированный tiebreak, §12.4).
    hits.sort(key=lambda h: (-h.score, h.doc_id))
    return hits
