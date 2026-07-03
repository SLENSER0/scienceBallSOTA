"""Spec-exact §12.4 positional **Borda-count** rank fusion.

Позиционный агрегатор рангов, отличный от reciprocal-rank
(:func:`kg_retrievers.fusion.rrf_fuse`) и score-based comb_fusion.

Идея Borda-count: в списке длины ``L`` элемент на позиции ``rank`` (0-indexed,
лучший = 0) получает ``L - rank`` очков — топ длинного списка даёт ``L`` очков,
последний — ``1``. Очки суммируются по всем спискам; итог сортируется по убыванию
очков, ничьи разрешаются по ``doc_id`` (лексикографически, меньший id раньше).

Pure python — no store/graph access; callers assemble the rankings dict.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before building the rankings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BordaResult:
    """One fused doc: суммарные ``points`` + число списков ``appearances`` (§12.4)."""

    doc_id: str
    points: float
    appearances: int

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug explainability (§12.4)."""
        return {
            "doc_id": self.doc_id,
            "points": self.points,
            "appearances": self.appearances,
        }


def borda_points(rank: int, list_len: int) -> int:
    """Borda points for a 0-indexed ``rank`` in a list of length ``list_len``.

    Очки §12.4: ``list_len - rank``. Топ элемент (``rank == 0``) списка длины ``L``
    получает ``L`` очков; элемент на позиции ``L-1`` — ``1``.
    """
    return list_len - rank


def borda_fuse(rankings: dict[str, list[str]]) -> list[BordaResult]:
    """Fuse ranked lists via un-weighted Borda-count (§12.4).

    Суммирует :func:`borda_points` по всем спискам ``rankings`` (values —
    упорядоченные списки ``doc_id``, лучший первым). Результат отсортирован по
    убыванию очков, ничьи — по возрастанию ``doc_id``. Документ, отсутствующий в
    каком-то списке, добавляет ``0`` очков из него.
    """
    return weighted_borda(rankings, dict.fromkeys(rankings, 1.0))


def weighted_borda(
    rankings: dict[str, list[str]],
    weights: dict[str, float],
) -> list[BordaResult]:
    """Fuse ranked lists via **weighted** Borda-count (§12.4).

    Как :func:`borda_fuse`, но очки каждого списка умножаются на ``weights[name]``
    (по умолчанию — вес ``0.0`` для непоименованных списков). Список с весом
    ``0.0`` не влияет на очки, но всё ещё считается в ``appearances``.
    """
    points: dict[str, float] = {}
    appearances: dict[str, int] = {}
    for name, ranked in rankings.items():
        weight = float(weights.get(name, 0.0))
        list_len = len(ranked)
        for rank, doc_id in enumerate(ranked):
            gained = borda_points(rank, list_len) * weight
            points[doc_id] = points.get(doc_id, 0.0) + gained
            appearances[doc_id] = appearances.get(doc_id, 0) + 1
    results = [
        BordaResult(doc_id=doc_id, points=points[doc_id], appearances=appearances[doc_id])
        for doc_id in points
    ]
    results.sort(key=lambda r: (-r.points, r.doc_id))
    return results
