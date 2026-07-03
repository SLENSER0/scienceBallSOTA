"""GraphRAG global-search cost estimator (§11.7).

Global search (глобальный поиск) over a GraphRAG community hierarchy runs a *map* step
over every community report and then a *reduce* step that folds the per-report answers
together in batches. Before spending real LLM calls this module gives a cheap, purely
arithmetic estimate of how many calls and tokens the run will cost, so a caller can
budget-gate a query or pick a smaller community level.

The map step issues exactly one call per report (один вызов на отчёт). The reduce step
folds those map answers in fixed-size batches, so it needs ``ceil(n_reports /
reduce_batch)`` calls. Prompt tokens are approximated from character length via a
``chars_per_token`` divisor; each call is assumed to emit ``response_tokens`` of output.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class CostEstimate:
    """One global-search cost estimate (§11.7).

    ``n_reports`` — number of community reports fed to the map step; ``map_calls`` —
    one LLM call per report; ``reduce_calls`` — batched fold calls
    (``ceil(n_reports / reduce_batch)``); ``total_calls`` — ``map + reduce``;
    ``est_prompt_tokens`` — summed report length divided by ``chars_per_token``;
    ``est_total_tokens`` — ``prompt + response_tokens * total_calls``.
    """

    n_reports: int
    map_calls: int
    reduce_calls: int
    total_calls: int
    est_prompt_tokens: int
    est_total_tokens: int

    def as_dict(self) -> dict:
        return {
            "n_reports": self.n_reports,
            "map_calls": self.map_calls,
            "reduce_calls": self.reduce_calls,
            "total_calls": self.total_calls,
            "est_prompt_tokens": self.est_prompt_tokens,
            "est_total_tokens": self.est_total_tokens,
        }


def estimate_global_search_cost(
    report_texts: list[str],
    *,
    chars_per_token: int = 4,
    reduce_batch: int = 10,
    response_tokens: int = 512,
) -> CostEstimate:
    """Estimate the call/token cost of a GraphRAG global search (§11.7).

    The map step issues one call per report, so ``map_calls == len(report_texts)``. The
    reduce step folds those answers in ``reduce_batch``-sized groups, needing
    ``ceil(n_reports / reduce_batch)`` calls (``0`` for an empty input). Prompt tokens
    are the sum of ``len(text) // chars_per_token`` over all reports, and total tokens
    add ``response_tokens`` of output for every call. An empty ``report_texts`` yields an
    all-zero estimate (пустой ввод — нулевая оценка).
    """
    n_reports = len(report_texts)
    map_calls = n_reports
    reduce_calls = ceil(n_reports / reduce_batch) if n_reports else 0
    total_calls = map_calls + reduce_calls

    est_prompt_tokens = sum(len(text) // chars_per_token for text in report_texts)
    est_total_tokens = est_prompt_tokens + response_tokens * total_calls

    return CostEstimate(
        n_reports=n_reports,
        map_calls=map_calls,
        reduce_calls=reduce_calls,
        total_calls=total_calls,
        est_prompt_tokens=est_prompt_tokens,
        est_total_tokens=est_total_tokens,
    )


def fits_budget(est: CostEstimate, max_calls: int) -> bool:
    """Return whether ``est`` stays within a ``max_calls`` budget (§11.7).

    ``True`` when ``est.total_calls <= max_calls`` (укладывается в бюджет), else
    ``False``. Used to tune ``reduce_batch`` / community level down until a query fits.
    """
    return est.total_calls <= max_calls
