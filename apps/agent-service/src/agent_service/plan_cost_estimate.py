"""§13.10 априорная оценка стоимости плана / a-priori QueryPlan cost estimate.

The §13.10 ``query_planner`` node emits a :class:`QueryPlan`; before the plan runs we
want a cheap, deterministic *a-priori* estimate of how costly / broad it will be. That
estimate feeds two consumers: the run log (§13.21) and the approval gate (§13.23), which
may pause an ``expensive`` plan for a human. This is **not** ``run_metrics`` — those are
*post-run* telemetry; here nothing has executed yet, so the number is derived purely from
the declared ``retrieval_strategy`` list.

The maths is pure-python (no graph store, no LLM), hence trivially unit-testable:

* ``base_cost`` — сумма :data:`STRATEGY_COST` по каждой стратегии плана / the sum of the
  per-strategy weights; an unknown strategy contributes ``0``;
* ``rerank_penalty`` — ``2`` when reranking is enabled, else ``0`` (реранк дороже);
* ``total`` — ``base_cost + rerank_penalty``;
* ``tier`` — ``cheap`` when ``total <= 2``, ``moderate`` when ``total <= 6``, otherwise
  ``expensive`` (порог одобрения / the approval threshold).

:class:`PlanCost` keeps every intermediate term so callers can render or log *why* a plan
landed in its tier; :meth:`PlanCost.as_dict` renders an orjson-safe plain dict.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Вес каждой стратегии извлечения / per-strategy cost weight (unknown strategies → 0).
STRATEGY_COST: dict[str, int] = {
    "cypher_template": 1,
    "evidence_lookup": 1,
    "gap_scan": 2,
    "hybrid_chunks": 3,
    "graphrag_community": 4,
    "graph_algo": 5,
}


@dataclass(frozen=True)
class PlanCost:
    """Разбор априорной стоимости плана / the a-priori QueryPlan cost breakdown.

    Every field is a plain ``int`` (``tier`` is a ``str``), so the dataclass is immutable
    and JSON-ready. ``total`` is the final value (``base_cost + rerank_penalty``) and
    ``tier`` is its bucket; the other fields explain how it was reached.
    """

    strategy_count: int
    base_cost: int
    rerank_penalty: int
    total: int
    tier: str

    def as_dict(self) -> dict[str, Any]:
        """Plain orjson-safe dict со всеми пятью полями / all five fields as a dict."""
        return {
            "strategy_count": self.strategy_count,
            "base_cost": self.base_cost,
            "rerank_penalty": self.rerank_penalty,
            "total": self.total,
            "tier": self.tier,
        }


def _tier_for(total: int) -> str:
    """Разложить итог по корзинам / bucket a total into cheap / moderate / expensive."""
    if total <= 2:
        return "cheap"
    if total <= 6:
        return "moderate"
    return "expensive"


def estimate_cost(plan: Mapping[str, Any], enable_rerank: bool = False) -> PlanCost:
    """Оценить стоимость плана до запуска / estimate a QueryPlan cost before it runs.

    ``base_cost`` is the sum of :data:`STRATEGY_COST` over each strategy listed in
    ``plan['retrieval_strategy']`` (an unknown strategy contributes ``0``, a missing key
    yields an empty list). ``rerank_penalty`` is ``2`` when ``enable_rerank`` is set, else
    ``0``; ``total = base_cost + rerank_penalty`` and ``tier`` follows the §13.23 approval
    thresholds (``<= 2`` cheap, ``<= 6`` moderate, otherwise expensive).

    :param plan: the QueryPlan mapping; only its ``retrieval_strategy`` list is read.
    :param enable_rerank: whether a reranking stage is enabled (adds the penalty).
    :returns: a :class:`PlanCost` carrying the counts, penalty, total and tier.
    """
    strategies = list(plan.get("retrieval_strategy", []))
    base_cost = sum(STRATEGY_COST.get(name, 0) for name in strategies)
    rerank_penalty = 2 if enable_rerank else 0
    total = base_cost + rerank_penalty

    return PlanCost(
        strategy_count=len(strategies),
        base_cost=base_cost,
        rerank_penalty=rerank_penalty,
        total=total,
        tier=_tier_for(total),
    )
