"""Tests for cross-unit measurement comparison — §7.5/§7.7 (contradiction detection).

Hand-checked cases: unit conversion feeds the ratio/relation classification, and
the interval/uncertainty helpers decide band overlap. RU/EN docstrings, <=100 chars.
"""

from __future__ import annotations

import math

import pytest

from kg_common.units.comparison import (
    MeasurementComparison,
    agreement_with_uncertainty,
    compare_values,
    intervals_overlap,
)


# --- spec assertions ---------------------------------------------------------
def test_celsius_kelvin_equal_agrees() -> None:
    """100 °C == 373.15 K — same temperature, agree (§7.5)."""
    result = compare_values(100, "°C", 373.15, "K")
    assert result.agree is True
    assert result.relation == "equal"


def test_mpa_kpa_equal_agrees() -> None:
    """1 MPa == 1000 kPa — pressure scale, agree (§7.5)."""
    assert compare_values(1, "MPa", 1000, "kPa").agree is True


def test_pressure_less_beyond_tolerance() -> None:
    """320 MPa vs 400 MPa: a < b past 5% tol → relation 'less', not agree (§7.7)."""
    result = compare_values(320, "MPa", 400, "MPa", rel_tol=0.05)
    assert result.relation == "less"
    assert result.agree is False


def test_length_nm_micrometre_equal() -> None:
    """1000 nm == 1 µm — length scale, agree (§7.5)."""
    assert compare_values(1000, "nm", 1, "µm").agree is True


def test_incompatible_dimensions_incomparable() -> None:
    """1 MPa vs 1 °C — different dimensions → incomparable (§7.5)."""
    assert compare_values(1, "MPa", 1, "°C").relation == "incomparable"


def test_intervals_overlap_true() -> None:
    """(10,20) and (15,25) share [15,20] → overlap (§7.7)."""
    assert intervals_overlap((10, 20), (15, 25)) is True


def test_intervals_overlap_false() -> None:
    """(10,20) and (25,30) are disjoint → no overlap (§7.7)."""
    assert intervals_overlap((10, 20), (25, 30)) is False


def test_agreement_with_uncertainty_true() -> None:
    """180±5 and 183±4 bands overlap → agree (§7.7)."""
    assert agreement_with_uncertainty(180, 5, 183, 4) is True


def test_agreement_with_uncertainty_false() -> None:
    """180±5 and 200±3 bands disjoint → no agree (§7.7)."""
    assert agreement_with_uncertainty(180, 5, 200, 3) is False


# --- ratio / delta / method detail -------------------------------------------
def test_incompatible_result_fields_are_null() -> None:
    """Incomparable verdict nulls ratio/delta/common_unit, method 'incompatible' (§7.5)."""
    result = compare_values(1, "MPa", 1, "°C")
    assert result.agree is False
    assert result.ratio is None
    assert result.delta is None
    assert result.common_unit is None
    assert result.method == "incompatible"


def test_unknown_unit_is_incomparable() -> None:
    """An unregistered unit is caught and treated as incomparable (§7.5)."""
    result = compare_values(1, "widgets", 1, "widgets")
    assert result.relation == "incomparable"
    assert result.method == "incompatible"


def test_ratio_and_common_unit_on_agreement() -> None:
    """Agreeing pair reports ratio≈1, common_unit = a's unit, method 'ratio' (§7.5)."""
    result = compare_values(1, "MPa", 1000, "kPa")
    assert result.common_unit == "MPa"
    assert result.method == "ratio"
    assert math.isclose(result.ratio, 1.0, rel_tol=1e-9)  # type: ignore[arg-type]


def test_delta_sign_follows_a_minus_b() -> None:
    """delta is a − b in a's unit: 320 − 400 MPa = −80 (§7.7)."""
    result = compare_values(320, "MPa", 400, "MPa")
    assert math.isclose(result.delta, -80.0, rel_tol=1e-9)  # type: ignore[arg-type]
    assert result.ratio is not None and result.ratio < 1.0


def test_greater_relation() -> None:
    """400 MPa vs 320 MPa: a > b past tol → relation 'greater' (§7.7)."""
    result = compare_values(400, "MPa", 320, "MPa")
    assert result.relation == "greater"
    assert result.agree is False


def test_within_tolerance_agrees_equal() -> None:
    """102 vs 100 MPa is within 5% → agree, relation 'equal' (§7.7)."""
    result = compare_values(102, "MPa", 100, "MPa", rel_tol=0.05)
    assert result.agree is True
    assert result.relation == "equal"


def test_just_outside_tolerance_disagrees() -> None:
    """106 vs 100 MPa is 6% apart, over 5% tol → disagree (§7.7)."""
    assert compare_values(106, "MPa", 100, "MPa", rel_tol=0.05).agree is False


def test_zero_b_uses_delta_method() -> None:
    """When converted b == 0, ratio is undefined → delta method (§7.5)."""
    result = compare_values(5, "MPa", 0, "MPa")
    assert result.ratio is None
    assert result.method == "delta"
    assert result.agree is False
    assert result.relation == "greater"


def test_both_zero_agree_via_delta() -> None:
    """0 vs 0 agrees through the delta fallback (§7.5)."""
    result = compare_values(0, "MPa", 0, "kPa")
    assert result.agree is True
    assert result.relation == "equal"
    assert result.method == "delta"


# --- helper edge cases -------------------------------------------------------
def test_intervals_touching_endpoint_overlaps() -> None:
    """Closed intervals touching at a point count as overlap (§7.7)."""
    assert intervals_overlap((10, 20), (20, 30)) is True


def test_intervals_unordered_endpoints() -> None:
    """Endpoint order does not matter: (20,10) == (10,20) (§7.7)."""
    assert intervals_overlap((20, 10), (25, 15)) is True


def test_uncertainty_touching_bands_agree() -> None:
    """Bands that just touch (180±5 vs 190±5) agree (§7.7)."""
    assert agreement_with_uncertainty(180, 5, 190, 5) is True


def test_uncertainty_negative_magnitude_used() -> None:
    """Negative uncertainty is taken by magnitude, not literally (§7.7)."""
    assert agreement_with_uncertainty(180, -5, 183, -4) is True


# --- dataclass surface -------------------------------------------------------
def test_as_dict_round_trip() -> None:
    """as_dict() exposes every field for JSON serialisation (§7.5)."""
    result = compare_values(1, "MPa", 1000, "kPa")
    data = result.as_dict()
    assert set(data) == {"agree", "relation", "ratio", "delta", "common_unit", "method"}
    assert data["agree"] is True
    assert data["common_unit"] == "MPa"


def test_comparison_is_frozen() -> None:
    """MeasurementComparison is immutable — frozen dataclass (house style)."""
    result = compare_values(1, "MPa", 1000, "kPa")
    with pytest.raises(AttributeError):
        result.agree = False  # type: ignore[misc]


def test_relation_always_in_allowed_set() -> None:
    """relation is always one of the four allowed labels (§7.5)."""
    allowed = {"equal", "greater", "less", "incomparable"}
    for r in (
        compare_values(100, "°C", 373.15, "K"),
        compare_values(320, "MPa", 400, "MPa"),
        compare_values(400, "MPa", 320, "MPa"),
        compare_values(1, "MPa", 1, "°C"),
    ):
        assert r.relation in allowed
        assert isinstance(r, MeasurementComparison)
