"""Tests for the SLO error-budget & burn-rate calculator — §23.16.

Every expected number is hand-checkable: with ``target = 0.99`` the budget is
exactly ``0.01``, so ``burn_rate`` is just ``observed_error_rate / 0.01`` (i.e.
``error_rate * 100``).
"""

from __future__ import annotations

import math

import pytest

from kg_common.slo_error_budget import FAST_BURN, ErrorBudget, evaluate


def test_exactly_on_budget_is_warning() -> None:
    # 990/1000 good => 1% error == the whole 1% budget => burn_rate 1.0.
    eb = evaluate(0.99, good=990, total=1000)
    assert eb.observed_success == 0.99
    assert math.isclose(eb.budget_total, 0.01)
    assert eb.burn_rate == 1.0
    assert eb.budget_remaining_fraction == 0.0
    assert eb.bad == 10
    assert eb.alert == "warning"


def test_perfect_window_leaves_full_budget() -> None:
    eb = evaluate(0.99, good=1000, total=1000)
    assert eb.observed_success == 1.0
    assert eb.burn_rate == 0.0
    assert eb.budget_consumed == 0.0
    assert eb.budget_remaining_fraction == 1.0
    assert eb.alert == "ok"


def test_ten_percent_errors_burn_ten_times() -> None:
    # 900/1000 => 10% error against a 1% budget => 10x burn, still warning.
    eb = evaluate(0.99, good=900, total=1000)
    assert math.isclose(eb.budget_consumed, 0.10)
    assert eb.burn_rate == 10.0
    assert eb.budget_remaining_fraction == 0.0  # clamped from 1 - 10 = -9
    assert eb.alert == "warning"


def test_fast_burn_is_critical() -> None:
    # 14.4% error against 1% budget => burn_rate 14.4 == fast-burn threshold.
    eb = evaluate(0.99, good=856, total=1000)
    assert math.isclose(eb.budget_consumed, 0.144)
    assert math.isclose(eb.burn_rate, FAST_BURN)
    assert eb.burn_rate >= FAST_BURN
    assert eb.alert == "critical"


def test_well_below_budget_is_ok() -> None:
    # 995/1000 => 0.5% error, half the 1% budget => burn_rate 0.5.
    eb = evaluate(0.99, good=995, total=1000)
    assert eb.burn_rate == 0.5
    assert eb.budget_remaining_fraction == 0.5
    assert eb.alert == "ok"


def test_remaining_fraction_clamped_when_overspent() -> None:
    # 500/1000 => 50% error, 50x over a 1% budget => remaining clamped to 0.0.
    eb = evaluate(0.99, good=500, total=1000)
    assert eb.burn_rate == 50.0
    assert eb.budget_remaining_fraction == 0.0
    assert eb.alert == "critical"


def test_total_zero_raises() -> None:
    with pytest.raises(ValueError, match="total"):
        evaluate(0.99, good=0, total=0)


@pytest.mark.parametrize("target", [0.0, 1.0, -0.1, 1.5])
def test_target_out_of_range_raises(target: float) -> None:
    with pytest.raises(ValueError, match="target"):
        evaluate(target, good=10, total=10)


def test_good_clamped_into_range() -> None:
    # good > total is clamped to total => a perfect window, no negative bad.
    eb = evaluate(0.99, good=1500, total=1000)
    assert eb.bad == 0
    assert eb.observed_success == 1.0
    assert eb.alert == "ok"


def test_as_dict_roundtrips_fields() -> None:
    eb = evaluate(0.99, good=990, total=1000)
    d = eb.as_dict()
    assert d == {
        "target": 0.99,
        "total": 1000,
        "bad": 10,
        "observed_success": 0.99,
        "budget_total": eb.budget_total,
        "budget_consumed": eb.budget_consumed,
        "budget_remaining_fraction": 0.0,
        "burn_rate": 1.0,
        "alert": "warning",
    }
    assert isinstance(eb, ErrorBudget)
