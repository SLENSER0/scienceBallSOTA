"""Tests for the answer-quality threshold sweep (§18.8)."""

from __future__ import annotations

import math

import pytest

from kg_eval.threshold_sweep import OperatingPoint, SweepReport, sweep_thresholds

# Canonical separable set: two positives above two negatives.
PAIRS: list[tuple[float, bool]] = [(0.9, True), (0.6, True), (0.4, False), (0.1, False)]


def test_best_point_is_perfect_at_0_6() -> None:
    """Threshold 0.6 admits both positives and no negatives — a perfect F1 point."""
    report = sweep_thresholds(PAIRS)
    assert isinstance(report, SweepReport)
    assert report.best.threshold == 0.6
    assert report.best.fbeta == 1.0
    assert report.best.precision == 1.0
    assert report.best.recall == 1.0


def test_all_positive_threshold_recall_one_precision_half() -> None:
    """At the lowest score everything is predicted positive: full recall, half precision."""
    report = sweep_thresholds(PAIRS)
    point = next(p for p in report.points if p.threshold == 0.1)
    assert point.recall == 1.0
    assert point.precision == 0.5
    assert point.tp == 2
    assert point.fp == 2
    assert point.fn == 0


def test_one_point_per_distinct_score() -> None:
    """Four distinct scores yield exactly four operating points."""
    report = sweep_thresholds(PAIRS)
    assert len(report.points) == 4
    assert {p.threshold for p in report.points} == {0.9, 0.6, 0.4, 0.1}


def test_beta_two_weights_recall() -> None:
    """At the recall-heavy all-positive threshold, F2 exceeds balanced F1."""
    f1 = sweep_thresholds(PAIRS, beta=1.0)
    f2 = sweep_thresholds(PAIRS, beta=2.0)
    p1 = next(p for p in f1.points if p.threshold == 0.1)
    p2 = next(p for p in f2.points if p.threshold == 0.1)
    # Same precision/recall (0.5 / 1.0), only the beta weighting differs.
    assert p1.precision == p2.precision == 0.5
    assert p1.recall == p2.recall == 1.0
    assert p2.fbeta > p1.fbeta
    # Hand check: F1 = 2/3, F2 = 5*0.5/(4*0.5+1) = 2.5/3.
    assert math.isclose(p1.fbeta, 2.0 / 3.0)
    assert math.isclose(p2.fbeta, 2.5 / 3.0)


def test_tp_plus_fn_constant_across_thresholds() -> None:
    """tp + fn is the fixed positive count (2) at every threshold."""
    report = sweep_thresholds(PAIRS)
    totals = {p.tp + p.fn for p in report.points}
    assert totals == {2}


def test_empty_pairs_raise() -> None:
    """Empty input is a caller bug."""
    with pytest.raises(ValueError):
        sweep_thresholds([])


def test_best_as_dict_reports_perfect_fbeta() -> None:
    """The serialised best point round-trips its perfect F-beta."""
    report = sweep_thresholds(PAIRS)
    assert report.best.as_dict()["fbeta"] == 1.0
    assert isinstance(report.best, OperatingPoint)


def test_tie_break_prefers_lowest_threshold() -> None:
    """When two thresholds share the top F-beta, the lower threshold wins."""
    # Labels desc-by-score are T,F,F,T. The high and low ends both reach F1 = 2/3:
    #   t=0.9 -> P=1, R=0.5, F1=2/3   (top positive only)
    #   t=0.3 -> P=0.5, R=1, F1=2/3   (all predicted positive)
    # 2/3 is the maximum over the sweep, so the tie is broken toward t=0.3.
    pairs = [(0.9, True), (0.7, False), (0.5, False), (0.3, True)]
    report = sweep_thresholds(pairs)
    top = max(p.fbeta for p in report.points)
    tied = [p.threshold for p in report.points if math.isclose(p.fbeta, top)]
    assert set(tied) == {0.9, 0.3}
    assert report.best.threshold == 0.3


def test_report_as_dict_structure() -> None:
    """The report serialises beta, all points, and the best point."""
    report = sweep_thresholds(PAIRS, beta=1.0)
    data = report.as_dict()
    assert data["beta"] == 1.0
    assert isinstance(data["points"], list)
    assert len(data["points"]) == 4
    assert data["best"]["threshold"] == 0.6
