"""Tests for the GraphRAG global-search cost estimator (§11.7)."""

from __future__ import annotations

import json

from kg_retrievers.graphrag_cost_estimate import (
    CostEstimate,
    estimate_global_search_cost,
    fits_budget,
)


def test_25_reports_batch_10() -> None:
    reports = ["report text" for _ in range(25)]
    est = estimate_global_search_cost(reports, reduce_batch=10)
    assert est.map_calls == 25
    assert est.reduce_calls == 3
    assert est.total_calls == 28


def test_empty_list_all_zero() -> None:
    est = estimate_global_search_cost([])
    assert est.n_reports == 0
    assert est.map_calls == 0
    assert est.reduce_calls == 0
    assert est.total_calls == 0
    assert est.est_prompt_tokens == 0
    assert est.est_total_tokens == 0


def test_400_char_report_contributes_100_prompt_tokens() -> None:
    est = estimate_global_search_cost(["x" * 400], chars_per_token=4)
    assert est.est_prompt_tokens == 100


def test_total_tokens_formula() -> None:
    reports = ["a" * 40, "b" * 80]  # 10 + 20 = 30 prompt tokens
    est = estimate_global_search_cost(
        reports, chars_per_token=4, reduce_batch=10, response_tokens=512
    )
    assert est.est_prompt_tokens == 30
    assert est.est_total_tokens == est.est_prompt_tokens + 512 * est.total_calls
    # 2 map + 1 reduce = 3 calls -> 30 + 512*3 = 1566
    assert est.est_total_tokens == 1566


def test_fits_budget_boundary() -> None:
    reports = ["r" for _ in range(25)]
    est = estimate_global_search_cost(reports, reduce_batch=10)  # total_calls == 28
    assert fits_budget(est, 28) is True
    assert fits_budget(est, 30) is True
    assert fits_budget(est, 27) is False


def test_reduce_calls_use_ceiling() -> None:
    reports = ["r" for _ in range(11)]
    est = estimate_global_search_cost(reports, reduce_batch=10)
    assert est.reduce_calls == 2
    assert est.map_calls == 11
    assert est.total_calls == 13


def test_as_dict_json_round_trips() -> None:
    est = estimate_global_search_cost(["x" * 400] * 3, reduce_batch=10)
    payload = est.as_dict()
    restored = json.loads(json.dumps(payload))
    assert restored == payload
    rebuilt = CostEstimate(**restored)
    assert rebuilt == est
