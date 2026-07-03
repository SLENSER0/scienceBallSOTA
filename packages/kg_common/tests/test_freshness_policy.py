"""Tests for wall-clock freshness SLA — тесты SLA свежести (§9.5)."""

from __future__ import annotations

import math

import pytest

from kg_common.freshness_policy import (
    FreshnessPolicy,
    is_overdue,
    minutes_late,
    next_deadline_epoch,
)


@pytest.mark.parametrize("bad_lag", [0.0, -1.0, -60.0])
def test_non_positive_lag_raises(bad_lag: float) -> None:
    """Zero/negative lag is rejected — неположительный лаг отвергается (§9.5)."""
    with pytest.raises(ValueError, match="must be positive"):
        FreshnessPolicy(maximum_lag_minutes=bad_lag)


def test_within_sla_not_late_not_overdue() -> None:
    """At t=3600s with lag=60 the asset is exactly on time (§9.5)."""
    policy = FreshnessPolicy(maximum_lag_minutes=60)
    # age = 3600s = 60 min, lag = 60 min -> exactly at deadline.
    assert minutes_late(0.0, 3600.0, policy) == 0.0
    assert is_overdue(0.0, 3600.0, policy) is False


def test_past_sla_is_late_and_overdue() -> None:
    """At t=7200s with lag=60 the asset is 60 minutes late (§9.5)."""
    policy = FreshnessPolicy(maximum_lag_minutes=60)
    # age = 7200s = 120 min, lag = 60 min -> 60 min late.
    assert minutes_late(0.0, 7200.0, policy) == 60.0
    assert is_overdue(0.0, 7200.0, policy) is True


def test_never_materialized_is_infinitely_late() -> None:
    """A None last-materialized epoch is infinitely late & overdue (§9.5)."""
    policy = FreshnessPolicy(maximum_lag_minutes=60)
    result = minutes_late(None, 7200.0, policy)
    assert math.isinf(result) and result > 0
    assert is_overdue(None, 7200.0, policy) is True


def test_next_deadline_epoch_adds_lag_seconds() -> None:
    """next_deadline_epoch(0, lag=30) == 1800.0 seconds (§9.5)."""
    policy = FreshnessPolicy(maximum_lag_minutes=30)
    assert next_deadline_epoch(0.0, policy) == 1800.0


def test_boundary_exactly_at_deadline_not_overdue() -> None:
    """now == last + lag*60 sits on the deadline, not past it (§9.5)."""
    policy = FreshnessPolicy(maximum_lag_minutes=45)
    last = 1000.0
    deadline = next_deadline_epoch(last, policy)  # 1000 + 2700 = 3700
    assert deadline == 3700.0
    assert minutes_late(last, deadline, policy) == 0.0
    assert is_overdue(last, deadline, policy) is False
    # One second past the deadline is overdue.
    assert is_overdue(last, deadline + 1.0, policy) is True


def test_as_dict_roundtrip() -> None:
    """as_dict exposes the lag verbatim — словарь отдаёт лаг (§9.5)."""
    policy = FreshnessPolicy(maximum_lag_minutes=60)
    assert policy.as_dict()["maximum_lag_minutes"] == 60
