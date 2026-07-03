"""Tests for the absence operating-point threshold sweep (§25.15)."""

from __future__ import annotations

from kg_eval.absence_threshold_sweep import (
    SweepPoint,
    ThresholdSweep,
    sweep_thresholds,
)

# Canonical two-row set: one true miss (high p) and one true gap (low p).
ROWS: list[dict] = [
    {"p_extractor_missed": 0.8, "gold": "possible_miss"},
    {"p_extractor_missed": 0.2, "gold": "genuine_gap"},
]


def _point_at(sweep: ThresholdSweep, threshold: float) -> SweepPoint:
    return next(p for p in sweep.points if p.threshold == threshold)


def test_threshold_zero_surfaces_every_miss() -> None:
    """At t=0.0 both cells are predicted possible_miss: no false gaps, full recall."""
    sweep = sweep_thresholds(ROWS)
    point = _point_at(sweep, 0.0)
    assert point.false_gap_rate == 0.0
    assert point.miss_recall == 1.0


def test_threshold_one_buries_every_miss() -> None:
    """At t=1.0 both cells fall below the cutoff → genuine_gap: max false gaps, no recall."""
    sweep = sweep_thresholds(ROWS)
    point = _point_at(sweep, 1.0)
    assert point.false_gap_rate == 1.0
    assert point.miss_recall == 0.0


def test_best_operating_point_avoids_false_gaps() -> None:
    """The tuner picks a threshold whose false_gap_rate is the achievable minimum 0.0."""
    sweep = sweep_thresholds(ROWS)
    assert isinstance(sweep, ThresholdSweep)
    assert sweep.best_false_gap_rate == 0.0
    # Lowest-threshold tie-break: t=0.0 already reaches the minimum.
    assert sweep.best_threshold == 0.0


def test_false_gap_rate_is_non_decreasing() -> None:
    """Raising t only moves cells miss→gap, so false_gap_rate never decreases."""
    sweep = sweep_thresholds(ROWS)
    rates = [p.false_gap_rate for p in sweep.points]
    assert rates == sorted(rates)


def test_points_match_threshold_grid() -> None:
    """Default grid is 0.0..1.0 step 0.05 → 21 points, each scoring n=2 rows."""
    sweep = sweep_thresholds(ROWS)
    assert len(sweep.points) == 21
    assert {p.threshold for p in sweep.points} == {round(i * 0.05, 2) for i in range(21)}
    assert all(p.n == 2 for p in sweep.points)


def test_custom_thresholds_control_point_count() -> None:
    """An explicit threshold list is honoured verbatim, one point per entry."""
    sweep = sweep_thresholds(ROWS, thresholds=[0.0, 0.5, 1.0])
    assert [p.threshold for p in sweep.points] == [0.0, 0.5, 1.0]
    # At t=0.5 the miss (p=0.8) is surfaced, the gap (p=0.2) is not: still no false gap.
    assert _point_at(sweep, 0.5).false_gap_rate == 0.0


def test_recall_and_false_gap_are_complementary() -> None:
    """false_gap_rate + miss_recall == 1 whenever any gold-possible_miss cell exists."""
    sweep = sweep_thresholds(ROWS)
    for point in sweep.points:
        assert point.false_gap_rate + point.miss_recall == 1.0


def test_empty_rows_have_no_zero_division() -> None:
    """Empty input scores false_gap_rate 0.0 (no misses to bury) with no ZeroDivision."""
    sweep = sweep_thresholds([])
    assert all(p.false_gap_rate == 0.0 for p in sweep.points)
    assert all(p.miss_recall == 0.0 for p in sweep.points)
    assert all(p.n == 0 for p in sweep.points)
    assert sweep.best_false_gap_rate == 0.0


def test_multiple_gold_misses_use_fractional_denominator() -> None:
    """With three gold misses, burying one yields false_gap_rate 1/3, recall 2/3."""
    rows = [
        {"p_extractor_missed": 0.9, "gold": "possible_miss"},
        {"p_extractor_missed": 0.7, "gold": "possible_miss"},
        {"p_extractor_missed": 0.3, "gold": "possible_miss"},
        {"p_extractor_missed": 0.1, "gold": "genuine_gap"},
    ]
    # At t=0.5 the p=0.3 miss is buried as genuine_gap; the other two are surfaced.
    point = _point_at(sweep_thresholds(rows), 0.5)
    assert abs(point.false_gap_rate - 1.0 / 3.0) < 1e-12
    assert abs(point.miss_recall - 2.0 / 3.0) < 1e-12
    assert point.n == 4


def test_as_dict_round_trips_structure() -> None:
    """SweepPoint.as_dict rounds rates; ThresholdSweep.as_dict nests all points."""
    sweep = sweep_thresholds(ROWS)
    data = sweep.as_dict()
    assert data["best_threshold"] == 0.0
    assert data["best_false_gap_rate"] == 0.0
    assert isinstance(data["points"], list)
    assert len(data["points"]) == 21
    first = data["points"][0]
    assert first == {"threshold": 0.0, "false_gap_rate": 0.0, "miss_recall": 1.0, "n": 2}
