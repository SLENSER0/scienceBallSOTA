"""Per-source candidate-budget allocation and truncation for the §12.1 orchestrator.

RU: Распределение бюджета кандидатов по источникам для оркестратора §12.1.
Каждый источник (dense/sparse/bm25/graph …) получает ``top_k`` кандидатов
(по умолчанию 100), общий бюджет = ``top_k`` * число источников, а ``rerank_top_n``
(по умолчанию 50) переносится дальше для стадии реранка §12. ``truncate`` обрезает
списки хитов каждого источника до его бюджета, сохраняя порядок; источник без
записи в бюджете отбрасывается.
EN: Per-source candidate-budget allocation for the §12.1 orchestrator. Each source
(dense/sparse/bm25/graph …) is given ``top_k`` candidates (default 100); the total
budget is ``top_k`` * number-of-sources, and ``rerank_top_n`` (default 50) is carried
forward to the §12 rerank stage. ``truncate`` caps each source's hit list to its
budget (order preserved); a source with no budget entry is dropped.

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read the rest via ``get_node()`` before
handing hit lists to :func:`truncate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# §12.1 orchestrator defaults: 100 candidates per source, keep top 50 for rerank.
DEFAULT_TOP_K = 100
DEFAULT_RERANK_TOP_N = 50


@dataclass(frozen=True)
class BudgetAllocation:
    """Frozen result of :func:`allocate` (§12.1).

    ``per_source`` maps each source name to its candidate budget; ``total`` is the
    summed budget across all sources; ``rerank_top_n`` is the cap carried to the §12
    rerank stage.
    """

    per_source: dict[str, int]
    total: int
    rerank_top_n: int

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§12.1, house style)."""
        return {
            "per_source": dict(self.per_source),
            "total": self.total,
            "rerank_top_n": self.rerank_top_n,
        }


def allocate(
    sources: list[str],
    *,
    top_k: int = DEFAULT_TOP_K,
    rerank_top_n: int = DEFAULT_RERANK_TOP_N,
) -> BudgetAllocation:
    """Allocate ``top_k`` candidates to each source (§12.1).

    Each source in ``sources`` receives ``top_k`` candidates; ``total`` is
    ``top_k * len(sources)`` and ``rerank_top_n`` is passed through unchanged.
    An empty ``sources`` list yields an empty ``per_source`` and ``total == 0``.
    Duplicate source names collapse to a single key (dict semantics).
    """
    per_source = dict.fromkeys(sources, top_k)
    total = top_k * len(per_source)
    return BudgetAllocation(
        per_source=per_source,
        total=total,
        rerank_top_n=rerank_top_n,
    )


def truncate(
    hits_by_source: dict[str, list],
    per_source: dict[str, int],
) -> dict[str, list]:
    """Cap each source's hit list to its budget, preserving order (§12.1).

    For every source in ``hits_by_source`` that also has a budget entry in
    ``per_source``, the list is sliced to its first ``per_source[source]`` hits.
    A list shorter than its budget is returned unchanged (a fresh copy). A source
    absent from ``per_source`` is dropped from the result entirely.
    """
    truncated: dict[str, list] = {}
    for source, hits in hits_by_source.items():
        if source not in per_source:
            continue  # No budget for this source -> drop it (§12.1).
        truncated[source] = list(hits[: per_source[source]])
    return truncated
