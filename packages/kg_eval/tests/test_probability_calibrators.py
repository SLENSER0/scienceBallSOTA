"""Tests for post-hoc confidence calibrators (§18.8).

Hand-checkable cases for histogram binning and isotonic (PAV) regression.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from kg_eval.probability_calibrators import (
    CalibrationMap,
    fit_histogram_binning,
    fit_isotonic,
)


def test_histogram_binning_maps_bins_to_empirical_rate() -> None:
    pairs = [(0.1, False), (0.2, False), (0.8, True), (0.9, True)]
    cal = fit_histogram_binning(pairs, n_bins=2)
    # Bin [0,0.5) has 0/2 positives; bin [0.5,1] has 2/2 positives.
    assert cal.apply(0.3) == 0.0
    assert cal.apply(0.85) == 1.0


def test_isotonic_pav_fitted_values() -> None:
    # Confidence-sorted targets [0,1,0,1,1] -> PAV pools the middle violation.
    pairs = [(0.1, False), (0.2, True), (0.3, False), (0.4, True), (0.5, True)]
    cal = fit_isotonic(pairs)
    fitted = [val for _conf, val in cal.knots]
    assert fitted == [0.0, 0.5, 0.5, 1.0, 1.0]


def test_isotonic_output_is_nondecreasing() -> None:
    pairs = [(0.05, False), (0.2, True), (0.35, False), (0.6, True), (0.9, True)]
    cal = fit_isotonic(pairs)
    values = [val for _conf, val in cal.knots]
    assert all(a <= b for a, b in pairwise(values))


def test_apply_is_monotone_clamped_above_one() -> None:
    cal = fit_histogram_binning([(0.9, True)], n_bins=4)
    assert cal.apply(1.5) <= 1.0


def test_apply_clamps_below_zero() -> None:
    cal = fit_histogram_binning([(0.1, True)], n_bins=4)
    # Negative input clamps to 0.0 then looks up the first knot's value.
    assert 0.0 <= cal.apply(-0.5) <= 1.0


def test_histogram_kind_label() -> None:
    cal = fit_histogram_binning([(0.5, True), (0.5, False)])
    assert cal.kind == "histogram_binning"


def test_isotonic_kind_label() -> None:
    cal = fit_isotonic([(0.5, True), (0.6, False)])
    assert cal.kind == "isotonic"


def test_empty_pairs_raise_value_error() -> None:
    with pytest.raises(ValueError):
        fit_histogram_binning([])
    with pytest.raises(ValueError):
        fit_isotonic([])


def test_as_dict_knots_round_trip_length_histogram() -> None:
    cal = fit_histogram_binning([(0.1, False), (0.9, True)], n_bins=10)
    d = cal.as_dict()
    assert d["kind"] == "histogram_binning"
    assert len(d["knots"]) == 10  # one knot per bin


def test_as_dict_knots_round_trip_length_isotonic() -> None:
    pairs = [(0.1, False), (0.4, True), (0.7, True)]
    cal = fit_isotonic(pairs)
    d = cal.as_dict()
    assert len(d["knots"]) == len(pairs)  # one knot per point


def test_calibration_map_is_frozen() -> None:
    cal = CalibrationMap(kind="isotonic", knots=((0.0, 0.0),))
    with pytest.raises((AttributeError, TypeError)):
        cal.kind = "other"  # type: ignore[misc]
