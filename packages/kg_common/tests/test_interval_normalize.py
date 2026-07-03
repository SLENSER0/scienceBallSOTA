"""Tests for §7.5 range / bound canonicalization (interval_normalize)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.units.conversions import convert
from kg_common.units.interval_normalize import NormalizedInterval, normalize_interval


def test_range_midpoint_percent() -> None:
    """12–28 % stays in %; value is the midpoint 20.0."""
    r = normalize_interval(12, 28, "%", "%")
    assert r.kind == "range"
    assert r.value == 20.0
    assert r.value_min == 12.0
    assert r.value_max == 28.0
    assert r.unit == "%"
    assert r.operator is None
    assert r.representative_source == "midpoint"


def test_lower_bound_operator() -> None:
    """>= 320 MPa is a one-sided bound; value is the bound itself."""
    r = normalize_interval(320, None, "MPa", "MPa", operator=">=")
    assert r.kind == "bound"
    assert r.value == 320.0
    assert r.operator == ">="
    assert r.value_min == 320.0
    assert r.value_max is None
    assert r.representative_source == "lower_bound"


def test_upper_bound_operator() -> None:
    """<= 5 %: bound whose representative value comes from the upper endpoint."""
    r = normalize_interval(None, 5, "%", "%", operator="<=")
    assert r.kind == "bound"
    assert r.value == 5.0
    assert r.operator == "<="
    assert r.value_min is None
    assert r.value_max == 5.0
    assert r.representative_source == "upper_bound"


def test_ppm_to_percent_conversion() -> None:
    """0–100 ppm converts into %: 100 ppm == 0.01 %."""
    r = normalize_interval(0, 100, "ppm", "%", converter=convert)
    assert r.value_min == 0.0
    assert r.value_max == 0.01
    assert r.kind == "range"
    assert r.value == pytest.approx(0.005)
    assert r.unit == "%"


def test_scalar_without_operator() -> None:
    """A lone endpoint with no operator is a plain scalar point value."""
    r = normalize_interval(7.5, None, "MPa", "MPa")
    assert r.kind == "scalar"
    assert r.value == 7.5
    assert r.operator is None
    assert r.representative_source == "value"


def test_range_conversion_midpoint_in_target() -> None:
    """Range endpoints converted, midpoint computed in the target unit."""
    # 1000–3000 ppm → 0.1–0.3 %, midpoint 0.2 %.
    r = normalize_interval(1000, 3000, "ppm", "%")
    assert r.value_min == pytest.approx(0.1)
    assert r.value_max == pytest.approx(0.3)
    assert r.value == pytest.approx(0.2)


def test_as_dict_roundtrip() -> None:
    """as_dict exposes every field for JSON serialization."""
    r = normalize_interval(12, 28, "%", "%")
    d = r.as_dict()
    assert d == {
        "kind": "range",
        "unit": "%",
        "value": 20.0,
        "value_min": 12.0,
        "value_max": 28.0,
        "operator": None,
        "representative_source": "midpoint",
    }


def test_frozen_dataclass() -> None:
    """NormalizedInterval is immutable (frozen)."""
    r = normalize_interval(320, None, "MPa", "MPa", operator=">=")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.value = 1.0  # type: ignore[misc]


def test_no_endpoints_raises() -> None:
    """At least one endpoint is required."""
    with pytest.raises(ValueError):
        normalize_interval(None, None, "%", "%")


def test_injected_converter_used() -> None:
    """The injected converter drives endpoint conversion (identity double here)."""

    def doubler(v: float, src: str, dst: str) -> float:
        return v * 2.0

    r = normalize_interval(10, 20, "x", "x", converter=doubler)
    assert r.value_min == 20.0
    assert r.value_max == 40.0
    assert r.value == 30.0
    assert isinstance(r, NormalizedInterval)
