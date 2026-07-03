"""Tests for LLM cost accounting — тесты учёта стоимости (§18.10)."""

from __future__ import annotations

import pytest

from kg_common.cost import (
    ModelPrice,
    UsageCost,
    aggregate_costs,
    cost_for,
    cost_per_unit,
)


def test_cost_for_prompt_only() -> None:
    """1000 prompt tokens @ 2.0/1k → 0.002 USD."""
    usage = cost_for("m", 1000, 0, {"m": ModelPrice("m", 2.0, 4.0)})
    assert usage.cost_usd == 0.002


def test_cost_for_completion_only() -> None:
    """500 completion tokens @ 4.0/1k → 0.002 USD."""
    usage = cost_for("m", 0, 500, {"m": ModelPrice("m", 2.0, 4.0)})
    assert usage.cost_usd == 0.002


def test_cost_for_both() -> None:
    """1000 prompt @ 2.0 + 1000 completion @ 4.0 → 0.006 USD."""
    usage = cost_for("m", 1000, 1000, {"m": ModelPrice("m", 2.0, 4.0)})
    assert usage.cost_usd == 0.006


def test_cost_for_unknown_model_raises() -> None:
    """Unknown model id raises KeyError — неизвестная модель → KeyError."""
    with pytest.raises(KeyError):
        cost_for("nope", 1, 1, {"m": ModelPrice("m", 2.0, 4.0)})


def test_aggregate_two_usages() -> None:
    """Two 0.002 usages of one model → total 0.004, single by_model key."""
    prices = {"m": ModelPrice("m", 2.0, 4.0)}
    usages = [cost_for("m", 1000, 0, prices), cost_for("m", 0, 500, prices)]
    agg = aggregate_costs(usages)
    assert agg["total_usd"] == 0.004
    assert agg["total_prompt_tokens"] == 1000
    assert agg["total_completion_tokens"] == 500
    assert len(agg["by_model"]) == 1
    assert agg["by_model"]["m"]["cost_usd"] == 0.004


def test_aggregate_empty() -> None:
    """Empty list → all-zero totals and empty by_model."""
    agg = aggregate_costs([])
    assert agg["total_usd"] == 0.0
    assert agg["total_prompt_tokens"] == 0
    assert agg["total_completion_tokens"] == 0
    assert agg["by_model"] == {}


def test_cost_per_unit() -> None:
    """0.006 over 3 units → 0.002; n_units=0 → 0.0."""
    usages = [cost_for("m", 1000, 1000, {"m": ModelPrice("m", 2.0, 4.0)})]
    assert cost_per_unit(usages, 3) == 0.002
    assert cost_per_unit(usages, 0) == 0.0


def test_as_dict_rounds_and_stable_keys() -> None:
    """as_dict()['cost_usd'] is a rounded float with fixed sorted-stable keys."""
    usage = UsageCost("m", 1000, 500, 0.0021234567)
    d = usage.as_dict()
    assert isinstance(d["cost_usd"], float)
    assert d["cost_usd"] == 0.002123
    assert list(d.keys()) == [
        "completion_tokens",
        "cost_usd",
        "model_id",
        "prompt_tokens",
    ]
