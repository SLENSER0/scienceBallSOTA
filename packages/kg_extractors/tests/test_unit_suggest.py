"""Unit suggestion for a bare property value (§7.14)."""

from __future__ import annotations

import dataclasses

from kg_extractors.unit_suggest import UnitSuggestion, suggest_unit


def test_hardness_suggests_hv() -> None:
    """A bare hardness (no value) defaults to the conventional HV (§7.14)."""
    s = suggest_unit("prop:hardness")
    assert s is not None
    assert s.unit == "HV"
    assert s.property_id == "prop:hardness"


def test_tensile_suggests_mpa() -> None:
    """Tensile strength defaults to MPa, the first allowed unit (§7.14)."""
    s = suggest_unit("prop:tensile_strength")
    assert s is not None
    assert s.unit == "MPa"


def test_unknown_property_returns_none() -> None:
    """An unknown / empty property has no allowed units → None (§7.14)."""
    assert suggest_unit("prop:does_not_exist") is None
    assert suggest_unit("") is None


def test_alternatives_are_the_other_allowed_units() -> None:
    """alternatives lists the remaining allowed units in vocab order (§7.14)."""
    s = suggest_unit("prop:hardness")
    assert s is not None
    assert s.alternatives == ("HB", "HRC")
    # The suggested unit is never repeated among its own alternatives.
    assert s.unit not in s.alternatives


def test_confidence_in_unit_interval() -> None:
    """Confidence is always within [0, 1] for varied inputs (§7.14)."""
    for pid, val in [
        ("prop:hardness", None),
        ("prop:hardness", 60),
        ("prop:elongation", None),
        ("prop:tensile_strength", 1.2),
        ("prop:density", 7800),
    ]:
        s = suggest_unit(pid, val)
        assert s is not None
        assert 0.0 <= s.confidence <= 1.0


def test_single_allowed_unit_is_fully_confident() -> None:
    """Elongation allows only "%", so it is suggested with confidence 1.0 (§7.14)."""
    s = suggest_unit("prop:elongation")
    assert s is not None
    assert s.unit == "%"
    assert s.confidence == 1.0
    assert s.alternatives == ()


def test_value_informed_tiebreak_hardness_hrc() -> None:
    """A hardness of 60 is a Rockwell-C number → HRC, not the default HV (§7.14)."""
    default = suggest_unit("prop:hardness")
    informed = suggest_unit("prop:hardness", 60)
    assert default is not None and informed is not None
    assert default.unit == "HV"
    assert informed.unit == "HRC"
    # The value hint raises confidence above the bare default.
    assert informed.confidence == 0.9
    assert informed.confidence > default.confidence
    # Alternatives now exclude the promoted HRC, in original order.
    assert informed.alternatives == ("HV", "HB")


def test_value_informed_tiebreak_density_kg_per_m3() -> None:
    """A density of 7800 brackets only kg/m3, promoting it over g/cm3 (§7.14)."""
    s = suggest_unit("prop:density", 7800)
    assert s is not None
    assert s.unit == "kg/m3"
    assert s.confidence == 0.9
    assert s.alternatives == ("g/cm3",)


def test_value_confirming_default_raises_confidence() -> None:
    """A hardness of 800 brackets only HV → default confirmed at confidence 0.9 (§7.14)."""
    s = suggest_unit("prop:hardness", 800)
    assert s is not None
    assert s.unit == "HV"
    assert s.confidence == 0.9


def test_ambiguous_value_keeps_default() -> None:
    """A hardness of 300 fits both HV and HB → tie unbroken, default HV at 0.5 (§7.14)."""
    s = suggest_unit("prop:hardness", 300)
    assert s is not None
    assert s.unit == "HV"
    assert s.confidence == 0.5


def test_non_numeric_value_is_ignored() -> None:
    """A non-numeric value cannot inform the guess → plain default (§7.14)."""
    s = suggest_unit("prop:hardness", "n/a")
    assert s is not None
    assert s.unit == "HV"
    assert s.confidence == 0.5


def test_as_dict_shape_and_values() -> None:
    """as_dict exposes property_id/unit/confidence/alternatives concretely (§7.14)."""
    s = suggest_unit("prop:hardness", 60)
    assert s is not None
    d = s.as_dict()
    assert set(d.keys()) == {"property_id", "unit", "confidence", "alternatives"}
    assert d["property_id"] == "prop:hardness"
    assert d["unit"] == "HRC"
    assert d["confidence"] == 0.9
    assert d["alternatives"] == ["HV", "HB"]


def test_suggestion_is_frozen() -> None:
    """UnitSuggestion is frozen — assignment raises (house style, §7.14)."""
    s = suggest_unit("prop:hardness")
    assert isinstance(s, UnitSuggestion)
    try:
        s.unit = "HB"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guard against a non-frozen regression
        raise AssertionError("UnitSuggestion must be frozen")
