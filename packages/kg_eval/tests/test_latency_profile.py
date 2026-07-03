"""Tests for latency percentile profiler + SLO gating (§23.9)."""

from __future__ import annotations

import pytest

from kg_eval.latency_profile import (
    LatencyProfile,
    SLOCheck,
    check_slo,
    percentile,
    profile,
)


def test_percentile_p50_odd_list() -> None:
    assert percentile([10, 20, 30, 40, 50], 50) == 30


def test_percentile_single_value() -> None:
    assert percentile([42.0], 99) == 42.0


def test_percentile_q_zero_returns_minimum() -> None:
    assert percentile([50, 10, 30, 20, 40], 0) == 10


def test_percentile_q_hundred_returns_maximum() -> None:
    assert percentile([50, 10, 30, 20, 40], 100) == 50


def test_percentile_empty_raises() -> None:
    with pytest.raises(ValueError):
        percentile([], 50)


def test_percentile_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], 150)


def test_profile_of_1_to_100() -> None:
    prof = profile(list(range(1, 101)))
    assert prof.n == 100
    assert prof.max == 100
    assert prof.min == 1
    assert prof.mean == 50.5
    assert prof.p50 == 50
    assert prof.p95 == 95
    assert prof.p99 == 99


def test_profile_percentiles_monotonic() -> None:
    prof = profile(list(range(1, 101)))
    assert prof.p99 >= prof.p95 >= prof.p50


def test_profile_empty_raises() -> None:
    with pytest.raises(ValueError):
        profile([])


def test_profile_as_dict_has_p95() -> None:
    prof = profile([1.0, 2.0, 3.0])
    d = prof.as_dict()
    assert "p95" in d
    assert set(d) == {"n", "mean", "p50", "p95", "p99", "max", "min"}


def test_check_slo_passes_when_within_threshold() -> None:
    prof = profile(list(range(1, 101)))  # p95 == 95
    result = check_slo(prof, metric="p95", threshold_ms=100)
    assert result.passed is True
    assert result.observed == 95
    assert result.threshold == 100


def test_check_slo_fails_when_above_threshold() -> None:
    prof = profile(list(range(1, 101)))  # p95 == 95
    result = check_slo(prof, metric="p95", threshold_ms=50)
    assert result.passed is False
    assert result.observed == 95


def test_check_slo_boundary_equal_passes() -> None:
    prof = profile(list(range(1, 101)))  # p95 == 95
    result = check_slo(prof, metric="p95", threshold_ms=95)
    assert result.passed is True


def test_check_slo_unknown_metric_raises() -> None:
    prof = profile([1.0, 2.0, 3.0])
    with pytest.raises((KeyError, ValueError)):
        check_slo(prof, metric="p42", threshold_ms=10)


def test_check_slo_default_metric_is_p95() -> None:
    prof = profile(list(range(1, 101)))
    result = check_slo(prof, threshold_ms=100)
    assert result.metric == "p95"


def test_slocheck_as_dict() -> None:
    prof = profile(list(range(1, 101)))
    d = check_slo(prof, metric="p99", threshold_ms=100).as_dict()
    assert d["passed"] is True
    assert d["metric"] == "p99"
    assert d["observed"] == 99
    assert d["threshold"] == 100


def test_frozen_dataclasses_immutable() -> None:
    prof = LatencyProfile(n=1, mean=1.0, p50=1.0, p95=1.0, p99=1.0, max=1.0, min=1.0)
    check = SLOCheck(passed=True, metric="p95", threshold=1.0, observed=1.0)
    with pytest.raises((AttributeError, Exception)):
        prof.n = 2  # type: ignore[misc]
    with pytest.raises((AttributeError, Exception)):
        check.passed = False  # type: ignore[misc]
