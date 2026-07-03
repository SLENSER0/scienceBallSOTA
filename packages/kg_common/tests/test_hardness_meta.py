"""Hardness-conversion metadata + spec parsing (§7.3)."""

from __future__ import annotations

import pytest

from kg_common.units.hardness_meta import (
    HardnessConversion,
    HardnessSpec,
    convert_with_metadata,
    parse_hardness_spec,
)


def test_conversion_carries_standard_and_method() -> None:
    c = convert_with_metadata(300, "HV", "HRC")
    assert isinstance(c, HardnessConversion)
    assert c.conversion_standard == "ASTM E140"
    assert c.normalization_method == "rule"
    assert c.from_scale == "HV" and c.to_scale == "HRC"
    assert c.value_in == 300.0
    assert 28 <= c.value_out <= 32  # HV300 ≈ HRC30 on the steel table


def test_way_out_value_flagged_out_of_range() -> None:
    c = convert_with_metadata(5000, "HV", "HRC")  # HV domain tops out at 800
    assert c.out_of_conversion_range is True
    assert "clamped" in c.note  # base converter clamps to the endpoint


def test_below_table_domain_flagged() -> None:
    c = convert_with_metadata(10, "HV", "HB")  # HV domain starts at 100
    assert c.out_of_conversion_range is True


def test_in_range_not_flagged() -> None:
    c = convert_with_metadata(300, "HV", "HRC")
    assert c.out_of_conversion_range is False


def test_conversion_as_dict_shape() -> None:
    d = convert_with_metadata(300, "HV", "HRC").as_dict()
    assert d["value_in"] == 300.0
    assert d["from_scale"] == "HV" and d["to_scale"] == "HRC"
    assert d["normalization_method"] == "rule"
    assert d["conversion_standard"] == "ASTM E140"
    assert d["out_of_conversion_range"] is False
    assert set(d) == {
        "value_in",
        "from_scale",
        "to_scale",
        "value_out",
        "normalization_method",
        "conversion_standard",
        "out_of_conversion_range",
        "note",
    }


def test_round_trip_hv_hb_hv_is_close() -> None:
    to_hb = convert_with_metadata(375, "HV", "HB").value_out
    back = convert_with_metadata(to_hb, "HB", "HV").value_out
    assert abs(back - 375) <= 10  # table interpolation is reversible within tolerance


def test_unsupported_scale_propagates_valueerror() -> None:
    with pytest.raises(ValueError, match="unsupported hardness scale"):
        convert_with_metadata(300, "HV", "MOHS")


def test_parse_brinell_indenter_load() -> None:
    spec = parse_hardness_spec("HBW 10/3000")
    assert spec == HardnessSpec("HB", indenter_load="10/3000")
    assert spec.load is None
    assert spec.as_dict() == {"scale": "HB", "indenter_load": "10/3000"}


def test_parse_vickers_loads() -> None:
    assert parse_hardness_spec("HV0.5") == HardnessSpec("HV", load=0.5)
    assert parse_hardness_spec("HV1") == HardnessSpec("HV", load=1.0)
    assert parse_hardness_spec("HV10") == HardnessSpec("HV", load=10.0)
    assert parse_hardness_spec("HV30") == HardnessSpec("HV", load=30.0)
    assert parse_hardness_spec("HV0.5").as_dict() == {"scale": "HV", "load": 0.5}


def test_parse_rockwell_no_load() -> None:
    spec = parse_hardness_spec("HRC")
    assert spec == HardnessSpec("HRC")
    assert spec.load is None and spec.indenter_load is None
    assert spec.as_dict() == {"scale": "HRC"}


def test_parse_is_case_insensitive_and_tolerates_spaces() -> None:
    assert parse_hardness_spec("  hv 5  ") == HardnessSpec("HV", load=5.0)
    assert parse_hardness_spec("hbs 2.5/187.5") == HardnessSpec("HB", indenter_load="2.5/187.5")


def test_parse_invalid_raises() -> None:
    with pytest.raises(ValueError, match="unrecognized hardness spec"):
        parse_hardness_spec("not-a-hardness")
