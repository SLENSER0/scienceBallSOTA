"""Tests for dimensional consistency checks (§7.15)."""

from __future__ import annotations

from kg_common.units.dimension_check import (
    HARDNESS,
    DimensionCheck,
    check_property_unit,
    dimension_for_property,
    dimension_for_unit,
    same_dimension,
)


def test_mpa_and_bar_are_same_dimension() -> None:
    # MPa and bar are both pressure — сопоставимы.
    assert same_dimension("MPa", "bar") is True
    assert dimension_for_unit("MPa") == "pressure"
    assert dimension_for_unit("bar") == "pressure"


def test_mpa_and_hv_differ_in_dimension() -> None:
    # pressure vs hardness — несопоставимы.
    assert same_dimension("MPa", "HV") is False
    assert dimension_for_unit("HV") == HARDNESS


def test_same_dimension_resolves_ru_aliases() -> None:
    # RU spellings fold to the same canonical dimension.
    assert same_dimension("МПа", "бар") is True
    assert same_dimension("МПа", "МПа") is True


def test_same_dimension_is_symmetric() -> None:
    pairs = [("MPa", "bar"), ("MPa", "HV"), ("degC", "K"), ("HV", "banana")]
    for a, b in pairs:
        assert same_dimension(a, b) == same_dimension(b, a)


def test_same_dimension_unknown_unit_is_false() -> None:
    assert same_dimension("MPa", "banana") is False
    assert same_dimension("banana", "banana") is False
    assert same_dimension(None, "MPa") is False


def test_property_unit_ok_tensile() -> None:
    res = check_property_unit("prop:tensile_strength", "MPa")
    assert res.ok is True
    assert res.expected_dimension == "pressure"
    assert res.actual_dimension == "pressure"


def test_property_unit_ok_hardness_and_temperature() -> None:
    hard = check_property_unit("prop:hardness", "HV")
    assert hard.ok is True
    assert hard.expected_dimension == HARDNESS
    temp = check_property_unit("prop:temperature", "degC")
    assert temp.ok is True
    assert temp.expected_dimension == "temperature"
    assert check_property_unit("prop:temperature", "K").ok is True


def test_property_unit_mismatch_is_flagged() -> None:
    res = check_property_unit("prop:tensile_strength", "HV")
    assert res.ok is False
    assert res.expected_dimension == "pressure"
    assert res.actual_dimension == HARDNESS


def test_unknown_property_and_unknown_unit() -> None:
    unknown_prop = check_property_unit("prop:nope", "MPa")
    assert unknown_prop.ok is False
    assert unknown_prop.expected_dimension is None
    unknown_unit = check_property_unit("prop:tensile_strength", "banana")
    assert unknown_unit.ok is False
    assert unknown_unit.expected_dimension == "pressure"
    assert unknown_unit.actual_dimension is None


def test_property_short_names_resolve() -> None:
    assert dimension_for_property("hardness") == HARDNESS
    assert dimension_for_property("tensile") == "pressure"
    assert dimension_for_property("temperature") == "temperature"
    assert dimension_for_property("nope") is None
    assert check_property_unit("tensile", "MPa").ok is True


def test_dimension_check_as_dict() -> None:
    res = check_property_unit("prop:tensile_strength", "MPa")
    d = res.as_dict()
    assert d == {
        "property_id": "prop:tensile_strength",
        "unit": "MPa",
        "ok": True,
        "expected_dimension": "pressure",
        "actual_dimension": "pressure",
        "reason": "unit 'MPa' matches expected dimension pressure",
    }
    assert isinstance(res, DimensionCheck)
