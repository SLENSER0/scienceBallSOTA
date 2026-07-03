"""Tests for absence probability-calibration reliability (§25.15)."""

from __future__ import annotations

import pytest

from kg_eval.absence_calibration_reliability import (
    CalibrationReport,
    ReliabilityBin,
    analyze,
    brier_score,
    expected_calibration_error,
    reliability_bins,
)


def test_brier_perfect_predictions_zero() -> None:
    rows = [{"p": 1.0, "outcome": 1}, {"p": 0.0, "outcome": 0}]
    assert brier_score(rows) == 0.0


def test_brier_single_half_miss() -> None:
    assert brier_score([{"p": 0.5, "outcome": 1}]) == 0.25


def test_brier_empty_is_zero() -> None:
    assert brier_score([]) == 0.0


def test_ece_perfectly_calibrated_zero() -> None:
    # Bin [0.0,0.1): two rows, mean_pred 0.0, mean_outcome 0.0.
    # Bin [0.9,1.0]: two rows, mean_pred 1.0, mean_outcome 1.0.
    rows = [
        {"p": 0.0, "outcome": 0},
        {"p": 0.0, "outcome": 0},
        {"p": 1.0, "outcome": 1},
        {"p": 1.0, "outcome": 1},
    ]
    assert expected_calibration_error(rows) == 0.0


def test_ece_empty_is_zero() -> None:
    assert expected_calibration_error([]) == 0.0


def test_bin_gap_equals_abs_mean_diff() -> None:
    # One bin [0.5,0.6) with preds 0.5,0.5 -> mean_pred 0.5; outcomes 1,0 -> 0.5.
    rows = [{"p": 0.5, "outcome": 1}, {"p": 0.5, "outcome": 0}]
    bins = reliability_bins(rows)
    b = bins[5]
    assert b.count == 2
    assert b.mean_pred == 0.5
    assert b.mean_outcome == 0.5
    assert b.gap == abs(b.mean_pred - b.mean_outcome)


def test_bin_gap_nonzero_hand_checked() -> None:
    # Bin [0.2,0.3): preds 0.2,0.2 -> mean 0.2; outcomes 1,0 -> mean 0.5; gap 0.3.
    rows = [{"p": 0.2, "outcome": 1}, {"p": 0.2, "outcome": 0}]
    b = reliability_bins(rows)[2]
    assert b.mean_pred == pytest.approx(0.2)
    assert b.mean_outcome == 0.5
    assert b.gap == pytest.approx(0.3)


def test_bin_counts_sum_to_n() -> None:
    rows = [
        {"p": 0.05, "outcome": 0},
        {"p": 0.35, "outcome": 1},
        {"p": 0.95, "outcome": 1},
        {"p": 1.0, "outcome": 0},
    ]
    bins = reliability_bins(rows)
    assert sum(b.count for b in bins) == len(rows)


def test_p_lands_in_bin_index_three() -> None:
    bins = reliability_bins([{"p": 0.3, "outcome": 1}], n_bins=10)
    b = bins[3]
    assert b.lo <= 0.3 < b.hi
    assert b.lo == pytest.approx(0.3)
    assert b.hi == pytest.approx(0.4)
    assert b.count == 1
    # No other bin captured the row.
    assert sum(x.count for x in bins) == 1


def test_probability_one_clamps_to_last_bin() -> None:
    bins = reliability_bins([{"p": 1.0, "outcome": 1}], n_bins=10)
    assert bins[-1].count == 1
    assert bins[-1].hi == 1.0
    assert sum(b.count for b in bins) == 1


def test_reliability_bins_length_is_n_bins() -> None:
    bins = reliability_bins([{"p": 0.5, "outcome": 1}], n_bins=4)
    assert len(bins) == 4


def test_reliability_bins_rejects_zero_bins() -> None:
    with pytest.raises(ValueError):
        reliability_bins([{"p": 0.5, "outcome": 1}], n_bins=0)


def test_analyze_bundles_report() -> None:
    rows = [{"p": 0.5, "outcome": 1}]
    report = analyze(rows)
    assert isinstance(report, CalibrationReport)
    assert report.n == 1
    assert report.brier == 0.25
    assert report.ece == pytest.approx(0.5)
    assert len(report.bins) == 10


def test_analyze_empty_all_zero() -> None:
    report = analyze([])
    assert report.n == 0
    assert report.ece == 0.0
    assert report.brier == 0.0
    assert len(report.bins) == 10


def test_as_dict_round_trips_keys() -> None:
    b = ReliabilityBin(0.3, 0.4, 1, 0.3, 1.0, 0.7)
    assert b.as_dict() == {
        "lo": 0.3,
        "hi": 0.4,
        "count": 1,
        "mean_pred": 0.3,
        "mean_outcome": 1.0,
        "gap": 0.7,
    }
    report = analyze([{"p": 0.3, "outcome": 1}])
    d = report.as_dict()
    assert set(d) == {"bins", "ece", "brier", "n"}
    assert isinstance(d["bins"], list)
