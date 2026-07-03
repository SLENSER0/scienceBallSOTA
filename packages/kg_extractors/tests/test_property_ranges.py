"""Property physical-range catalog YAML + loader (§7.13)."""

from __future__ import annotations

from pathlib import Path

from kg_extractors.property_ranges import (
    PropertyRange,
    PropertyRanges,
    default_property_ranges,
    in_hard_range,
    load_property_ranges,
    range_for,
)

_EXPECTED_IDS = {
    "prop:hardness",
    "prop:tensile_strength",
    "prop:yield_strength",
    "prop:elongation",
    "prop:conductivity",
    "prop:density",
}

_RESOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "kg_extractors"
    / "resources"
    / "property_ranges.yaml"
)


def test_ranges_load() -> None:
    ranges = load_property_ranges()
    assert isinstance(ranges, PropertyRanges)
    assert len(ranges) == 6
    assert all(isinstance(ranges.entry(i), PropertyRange) for i in ranges.all_ids())


def test_hardness_range_present() -> None:
    ranges = load_property_ranges()
    hardness = ranges.entry("prop:hardness")
    assert hardness is not None
    assert hardness.hard_min == 0.0
    assert hardness.hard_max == 10000.0
    assert ranges.range_for("prop:hardness") == (0.0, 10000.0)


def test_in_hard_range_true_within() -> None:
    ranges = load_property_ranges()
    # 200 HV is a perfectly ordinary steel hardness -> inside [0, 10000].
    assert ranges.in_hard_range("prop:hardness", 200.0) is True
    # boundary values are inclusive.
    assert ranges.in_hard_range("prop:hardness", 0.0) is True
    assert ranges.in_hard_range("prop:hardness", 10000.0) is True


def test_in_hard_range_false_outside() -> None:
    ranges = load_property_ranges()
    # 99999 HV and negatives are non-physical -> outside [0, 10000].
    assert ranges.in_hard_range("prop:hardness", 99999.0) is False
    assert ranges.in_hard_range("prop:hardness", -5.0) is False


def test_unknown_property_returns_none() -> None:
    ranges = load_property_ranges()
    assert ranges.range_for("prop:does_not_exist") is None
    assert ranges.entry("prop:does_not_exist") is None
    # unknown id has no bounds to satisfy -> membership is False.
    assert ranges.in_hard_range("prop:does_not_exist", 1.0) is False


def test_typical_band_present() -> None:
    ranges = load_property_ranges()
    assert ranges.typical_for("prop:hardness") == (50.0, 900.0)
    # typical band is a strict subset of the hard range.
    assert ranges.in_typical_band("prop:hardness", 200.0) is True
    # 9500 HV is inside hard range but outside the typical band.
    assert ranges.in_hard_range("prop:hardness", 9500.0) is True
    assert ranges.in_typical_band("prop:hardness", 9500.0) is False


def test_at_least_six_properties() -> None:
    ranges = load_property_ranges()
    assert len(ranges) >= 6
    assert _EXPECTED_IDS.issubset(set(ranges.all_ids()))


def test_unit_stored() -> None:
    ranges = load_property_ranges()
    assert ranges.unit_for("prop:hardness") == "HV"
    assert ranges.unit_for("prop:tensile_strength") == "MPa"
    assert ranges.unit_for("prop:elongation") == "%"
    assert ranges.unit_for("prop:density") == "g/cm3"


def test_deterministic() -> None:
    first = load_property_ranges()
    second = load_property_ranges()
    assert first.all_ids() == second.all_ids()
    assert first.as_dict() == second.as_dict()
    # file order is preserved: hardness is first in the YAML.
    assert first.all_ids()[0] == "prop:hardness"


def test_density_range_hand_checked() -> None:
    ranges = load_property_ranges()
    density = ranges.entry("prop:density")
    assert density is not None
    assert density.hard_range() == (0.1, 25.0)
    assert density.typical_band() == (0.5, 22.0)
    # water (1.0) and osmium (~22.6) are within hard range; 30 g/cm3 is not.
    assert ranges.in_hard_range("prop:density", 1.0) is True
    assert ranges.in_hard_range("prop:density", 22.6) is True
    assert ranges.in_hard_range("prop:density", 30.0) is False


def test_module_level_helpers_use_default_catalog() -> None:
    assert range_for("prop:tensile_strength") == (0.0, 10000.0)
    assert in_hard_range("prop:tensile_strength", 500.0) is True
    assert in_hard_range("prop:tensile_strength", -1.0) is False
    assert range_for("prop:missing") is None
    # cached default is a genuine PropertyRanges catalog.
    assert isinstance(default_property_ranges(), PropertyRanges)


def test_resource_yaml_exists_and_is_mapping() -> None:
    assert _RESOURCE.is_file()
    ranges = load_property_ranges(_RESOURCE)
    assert ranges.all_ids() == default_property_ranges().all_ids()
