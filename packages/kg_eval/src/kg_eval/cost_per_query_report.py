"""Cost/query baseline benchmark metric from per-call LLM records (§23.10).

Агрегирует поштучные записи о вызовах LLM (токены и стоимость) в метрику
«стоимость на запрос». Записи группируются по ``query_id``: стоимость и токены
суммируются в пределах одного запроса (несколько вызовов = один запрос). Затем
по стоимостям запросов считаются среднее и p95 методом «ближайшего ранга»
(nearest-rank). ``over_budget`` истинно, если среднее превышает ``budget_per_query``
(при ``None`` бюджета — всегда ложно). Это НЕ :mod:`baseline_benchmark` (сравнение
N систем): здесь одна метрика стоимости с проверкой бюджета.

Aggregates per-call LLM token/cost records into a cost-per-query benchmark
metric. Records are grouped by ``query_id``: cost and tokens are summed within a
query (several calls = one query). Mean and nearest-rank p95 are computed over the
per-query costs. ``over_budget`` is true iff the mean exceeds ``budget_per_query``
(always false when the budget is ``None``). Distinct from :mod:`baseline_benchmark`
(N-system comparison): this is a single cost metric with a budget check.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# USD amounts rounded before display so sub-cent float noise does not leak into
# reports; per-query cent-fractions stay well within 6 decimal places.
_USD_NDIGITS = 6


@dataclass(frozen=True)
class CostReport:
    """Cost/query benchmark verdict — среднее, p95 и проверка бюджета (§23.10).

    ``n_queries`` is the count of distinct ``query_id`` values. ``total_cost_usd``
    and ``total_tokens`` sum across every call. ``mean_cost_per_query`` and
    ``p95_cost_per_query`` are computed over the per-query cost totals (p95 by
    nearest-rank). ``budget_per_query`` echoes the checked budget (``None`` if
    unset). ``over_budget`` is true iff the mean strictly exceeds that budget
    (false when no budget was given).
    """

    n_queries: int
    total_cost_usd: float
    mean_cost_per_query: float
    p95_cost_per_query: float
    total_tokens: int
    budget_per_query: float | None
    over_budget: bool

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready), 7 keys; USD fields rounded to 6 dp."""
        budget = self.budget_per_query
        return {
            "n_queries": self.n_queries,
            "total_cost_usd": round(self.total_cost_usd, _USD_NDIGITS),
            "mean_cost_per_query": round(self.mean_cost_per_query, _USD_NDIGITS),
            "p95_cost_per_query": round(self.p95_cost_per_query, _USD_NDIGITS),
            "total_tokens": self.total_tokens,
            "budget_per_query": None if budget is None else round(budget, _USD_NDIGITS),
            "over_budget": self.over_budget,
        }


def aggregate(
    records: Sequence[Mapping[str, object]],
    *,
    budget_per_query: float | None = None,
) -> CostReport:
    """Aggregate per-call ``records`` into a :class:`CostReport` (§23.10).

    Записи группируются по ключу ``query_id``; ``cost_usd`` и ``tokens`` каждой
    записи суммируются в стоимость и токены соответствующего запроса. Среднее —
    сумма стоимостей запросов, делённая на число запросов; p95 — стоимость
    запроса с рангом ``ceil(0.95 * n)`` (ближайший ранг) в отсортированном по
    возрастанию списке. Пустой вход даёт все нули и ``over_budget=False``.
    ``over_budget`` истинно, только если задан бюджет и среднее строго больше него.

    Records are grouped by ``query_id``; each record's ``cost_usd`` and ``tokens``
    add to that query's totals. The mean is the sum of per-query costs over the
    query count; p95 is the cost at nearest-rank ``ceil(0.95 * n)`` in the
    ascending per-query cost list. Empty input yields all-zero fields and
    ``over_budget=False``. ``over_budget`` is true only when a budget was given
    and the mean strictly exceeds it.
    """
    per_query_cost: dict[object, float] = {}
    total_tokens = 0
    for rec in records:
        qid = rec["query_id"]
        per_query_cost[qid] = per_query_cost.get(qid, 0.0) + float(rec.get("cost_usd", 0.0))
        total_tokens += int(rec.get("tokens", 0))

    n_queries = len(per_query_cost)
    costs = sorted(per_query_cost.values())
    total_cost = math.fsum(costs)
    if n_queries == 0:
        mean_cost = 0.0
        p95_cost = 0.0
    else:
        mean_cost = total_cost / n_queries
        # Nearest-rank: rank in 1..n, index rank-1; p95 of a single query is that query.
        rank = math.ceil(0.95 * n_queries)
        p95_cost = costs[rank - 1]

    over_budget = budget_per_query is not None and mean_cost > budget_per_query
    return CostReport(
        n_queries=n_queries,
        total_cost_usd=total_cost,
        mean_cost_per_query=mean_cost,
        p95_cost_per_query=p95_cost,
        total_tokens=total_tokens,
        budget_per_query=budget_per_query,
        over_budget=over_budget,
    )
