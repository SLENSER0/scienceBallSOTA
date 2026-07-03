"""Tests for confidence calibration + uncertainty model (§23.25)."""

from __future__ import annotations

import pytest

from kg_eval.calibration_ece import (
    Bin,
    CalibrationReport,
    brier_score,
    calibration_report,
    expected_calibration_error,
    max_calibration_error,
    reliability_bins,
)


def test_perfectly_calibrated_zero_ece_and_brier() -> None:
    pairs = [(0.0, False), (1.0, True)]
    assert expected_calibration_error(pairs) == 0.0
    assert brier_score(pairs) == 0.0


def test_fully_miscalibrated_ece_mce_brier_one() -> None:
    pairs = [(1.0, False), (0.0, True)]
    assert expected_calibration_error(pairs) == 1.0
    assert max_calibration_error(pairs) == 1.0
    assert brier_score(pairs) == 1.0


def test_brier_score_single_half_confidence() -> None:
    assert brier_score([(0.5, True)]) == 0.25


def test_reliability_bins_two_bins_placement() -> None:
    bins = reliability_bins([(0.3, True), (0.8, False)], n_bins=2)
    assert len(bins) == 2
    # 0.3 -> bin0, 0.8 -> bin1
    assert bins[0].count == 1
    assert bins[0].avg_confidence == 0.3
    assert bins[1].count == 1
    assert bins[1].avg_confidence == 0.8


def test_confidence_exactly_one_lands_in_last_bin() -> None:
    bins = reliability_bins([(1.0, True)], n_bins=10)
    assert bins[-1].count == 1
    assert bins[-1].hi == 1.0
    # no other bin captured it
    assert sum(b.count for b in bins) == 1


def test_empty_bins_have_zeroed_stats() -> None:
    bins = reliability_bins([(0.05, True)], n_bins=4)
    assert bins[0].count == 1
    for b in bins[1:]:
        assert b.count == 0
        assert b.avg_confidence == 0.0
        assert b.accuracy == 0.0


def test_bin_bounds_are_equal_width() -> None:
    bins = reliability_bins([(0.5, True)], n_bins=4)
    assert bins[0].lo == 0.0
    assert bins[0].hi == 0.25
    assert bins[3].lo == 0.75
    assert bins[3].hi == 1.0


def test_empty_input_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        reliability_bins([])
    with pytest.raises(ValueError):
        expected_calibration_error([])
    with pytest.raises(ValueError):
        max_calibration_error([])
    with pytest.raises(ValueError):
        brier_score([])
    with pytest.raises(ValueError):
        calibration_report([])


def test_report_n_equals_len_pairs() -> None:
    pairs = [(0.1, False), (0.4, True), (0.9, True)]
    report = calibration_report(pairs)
    assert report.n == len(pairs)
    assert report.n_bins == 10


def test_as_dict_ece_round_trips() -> None:
    pairs = [(0.2, True), (0.7, False), (0.9, True)]
    report = calibration_report(pairs)
    assert report.as_dict()["ece"] == report.ece
    assert report.as_dict()["mce"] == report.mce
    assert report.as_dict()["brier"] == report.brier


def test_bin_as_dict_shape() -> None:
    b = Bin(lo=0.0, hi=0.5, count=2, avg_confidence=0.25, accuracy=0.5)
    d = b.as_dict()
    assert d == {
        "lo": 0.0,
        "hi": 0.5,
        "count": 2,
        "avg_confidence": 0.25,
        "accuracy": 0.5,
    }


def test_report_is_frozen_dataclass() -> None:
    report = calibration_report([(0.5, True)])
    assert isinstance(report, CalibrationReport)
    with pytest.raises(AttributeError):
        report.ece = 0.9  # type: ignore[misc]


def test_report_bins_length_matches_n_bins() -> None:
    report = calibration_report([(0.5, True), (0.1, False)], n_bins=5)
    assert len(report.bins) == 5
    assert report.as_dict()["bins"][0]["lo"] == 0.0


def test_ece_manual_weighted_gap() -> None:
    # bin0: [(0.1,True)] -> acc=1.0, conf=0.1, gap=0.9, weight=1/3
    # bin1 (0.4->bin4 with n_bins=10): conf=0.4,label False acc=0, gap=0.4
    # Use n_bins=2 for a hand check.
    pairs = [(0.1, True), (0.1, False), (0.9, True)]
    # n_bins=2: bin0 has (0.1,True),(0.1,False): conf=0.1 acc=0.5 gap=0.4 count=2
    #           bin1 has (0.9,True): conf=0.9 acc=1.0 gap=0.1 count=1
    ece = expected_calibration_error(pairs, n_bins=2)
    expected = (2 / 3) * 0.4 + (1 / 3) * 0.1
    assert ece == pytest.approx(expected)
    mce = max_calibration_error(pairs, n_bins=2)
    assert mce == pytest.approx(0.4)
