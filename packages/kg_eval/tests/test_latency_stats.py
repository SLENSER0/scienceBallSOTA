"""Tests for latency percentile summary (§18.5)."""

from __future__ import annotations

from kg_eval.latency_stats import LatencySummary, percentile, summarize_latencies


def test_percentile_median_interpolated() -> None:
    # rank = 3 * 0.5 = 1.5 -> halfway between 20 and 30 = 25.0
    assert percentile([10, 20, 30, 40], 0.5) == 25.0


def test_percentile_single_element_any_q() -> None:
    for q in (0.0, 0.25, 0.5, 0.95, 1.0):
        assert percentile([42.0], q) == 42.0


def test_summarize_p50_max_count() -> None:
    s = summarize_latencies([100, 200, 300, 400, 500])
    assert s.p50 == 300.0
    assert s.max == 500.0
    assert s.count == 5


def test_summarize_mean() -> None:
    s = summarize_latencies([100, 200, 300, 400, 500])
    assert s.mean == 300.0


def test_slo_violations_counts_above_threshold() -> None:
    s = summarize_latencies([100, 200, 300, 400, 500], slo_ms=350)
    assert s.slo_violations == 2  # 400 and 500 exceed 350


def test_slo_none_no_violations() -> None:
    s = summarize_latencies([100, 200, 300, 400, 500], slo_ms=None)
    assert s.slo_violations == 0
    assert s.slo_ms is None


def test_empty_samples_zeroed_no_error() -> None:
    s = summarize_latencies([])
    assert s.count == 0
    assert s.p50 == 0.0
    assert s.p95 == 0.0
    assert s.p99 == 0.0
    assert s.mean == 0.0
    assert s.max == 0.0
    assert s.slo_violations == 0


def test_as_dict_types_and_rounding() -> None:
    s = summarize_latencies([100, 200, 300, 400, 500], slo_ms=350)
    d = s.as_dict()
    assert isinstance(d["count"], int) and d["count"] == 5
    assert isinstance(d["p95"], float)
    # p95 rank = 4 * 0.95 = 3.8 -> 400 + 0.8*(500-400) = 480.0
    assert d["p95"] == 480.0
    assert isinstance(s, LatencySummary)
