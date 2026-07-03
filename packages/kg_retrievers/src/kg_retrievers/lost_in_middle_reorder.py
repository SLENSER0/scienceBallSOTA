"""Positional context-packing reorder against the 'lost-in-the-middle' bias (§12.9).

LLM-контекст: модель хуже всего «видит» середину длинного окна, а лучше всего — начало и
конец. Этот шаг переупорядочивает уже отранжированные хиты так, чтобы самые релевантные
попадали в «голову» и «хвост» промпта, а наименее релевантные — в середину, где внимание
модели проседает.

Distinct from :mod:`kg_retrievers.rerank_diversity` (MMR — trades relevance for novelty):
here relevance order is preserved, only the *packing position* changes.

- :func:`fold_order` — «складывание» («interleave from both ends»): rank0 → position 0,
  rank1 → last, rank2 → position 1, rank3 → second-last, … alternating outward-in, so the
  best-ranked ids sit at the extremes and the worst land in the middle.
- :func:`reorder_hits` — sorts scored hit dicts by descending ``score`` (stable on ties),
  folds their ids, and returns a frozen :class:`ReorderResult`.

Pure python — no numpy, no store/graph access. Callers assemble the scored hit dicts.
Kuzu note: custom node props are not queryable columns — callers RETURN base columns and
read the rest via ``get_node()`` before building the hit dicts fed here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReorderResult:
    """Frozen result of a lost-in-the-middle packing reorder (§12.9).

    ``order`` is the folded id sequence (packing order). ``head_ids`` is the first
    ``ceil(n/2)`` ids of the fold (front of the prompt window), ``tail_ids`` the remainder
    (end of the window). The most relevant ids populate the head/tail extremes.
    """

    order: tuple[str, ...]
    head_ids: tuple[str, ...]
    tail_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": list(self.order),
            "head_ids": list(self.head_ids),
            "tail_ids": list(self.tail_ids),
        }


def _score_of(hit: Mapping[str, Any], score_key: str) -> float:
    """Extract a hit's relevance score, defaulting to 0.0 if absent/non-numeric."""
    val = hit.get(score_key, 0.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def fold_order(ranked_ids: Sequence[str]) -> list[str]:
    """Interleave a rank-ordered id list outward-in for context packing (§12.9).

    Places ``ranked_ids[0]`` at position 0, ``ranked_ids[1]`` at the last position,
    ``ranked_ids[2]`` at position 1, ``ranked_ids[3]`` at the second-last, and so on —
    alternating from both ends toward the middle. The result is a new list of the same
    length; the least-relevant ids end up in the middle. Empty input → ``[]``.

    Example: ``fold_order(['a','b','c','d','e']) == ['a','c','e','d','b']``.
    """
    ids = list(ranked_ids)
    n = len(ids)
    if n == 0:
        return []
    result: list[str | None] = [None] * n
    front, back = 0, n - 1
    for i, id_ in enumerate(ids):
        if i % 2 == 0:
            result[front] = id_
            front += 1
        else:
            result[back] = id_
            back -= 1
    # Every slot filled exactly once (front/back sweep meets in the middle).
    return [id_ for id_ in result if id_ is not None]


def reorder_hits(
    hits: Sequence[Mapping[str, Any]],
    *,
    score_key: str = "score",
    id_key: str = "id",
) -> ReorderResult:
    """Reorder scored hits into a lost-in-the-middle packing (§12.9).

    Sorts ``hits`` by descending ``score_key`` (stable — ties keep input order), then folds
    the resulting ids via :func:`fold_order`, so the best-scored id lands at position 0 and
    the second-best at the last position. ``head_ids`` is the first ``ceil(n/2)`` folded
    ids, ``tail_ids`` the rest. Empty input → an all-empty :class:`ReorderResult`.
    """
    items = list(hits)
    order = sorted(range(len(items)), key=lambda i: (-_score_of(items[i], score_key), i))
    ranked_ids = [str(items[i][id_key]) for i in order]
    folded = fold_order(ranked_ids)
    n = len(folded)
    split = (n + 1) // 2  # ceil(n/2)
    return ReorderResult(
        order=tuple(folded),
        head_ids=tuple(folded[:split]),
        tail_ids=tuple(folded[split:]),
    )
