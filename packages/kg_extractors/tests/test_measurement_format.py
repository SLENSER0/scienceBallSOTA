"""Tests for canonical measurement formatting + parse-back (§7.16)."""

from __future__ import annotations

import pytest

from kg_extractors.measurement_format import (
    ParsedMeasurement,
    format_measurement,
    parse_back,
)


def test_value_plus_unit() -> None:
    """Scalar + unit renders as ``"148 HV"`` (целое без ``.0``)."""
    assert format_measurement(148, "HV") == "148 HV"
    assert format_measurement(148.0, "HV") == "148 HV"


def test_uncertainty() -> None:
    """``±`` uncertainty renders as ``"148 ± 5 HV"``."""
    assert format_measurement(148, "HV", uncertainty=5) == "148 ± 5 HV"


def test_range() -> None:
    """A 2-item range renders as ``"200-300 MPa"``."""
    assert format_measurement((200, 300), "MPa") == "200-300 MPa"
    assert format_measurement([200, 300], "MPa") == "200-300 MPa"


def test_no_unit() -> None:
    """Missing/empty unit is omitted (без единицы)."""
    assert format_measurement(7) == "7"
    assert format_measurement(7, "") == "7"
    assert format_measurement(7, None, uncertainty=1) == "7 ± 1"


def test_negative() -> None:
    """Negative values keep their sign, round-trip through parse_back."""
    assert format_measurement(-40, "C") == "-40 C"
    parsed = parse_back("-40 C")
    assert parsed["value"] == -40.0
    assert parsed["unit"] == "C"


def test_parse_back_uncertainty() -> None:
    """parse_back recovers value, uncertainty and unit."""
    parsed = parse_back("148 ± 5 HV")
    assert parsed == {
        "kind": "value",
        "value": 148.0,
        "low": None,
        "high": None,
        "unit": "HV",
        "uncertainty": 5.0,
    }


def test_parse_back_range() -> None:
    """parse_back recovers range bounds and unit."""
    parsed = parse_back("200-300 MPa")
    assert parsed["kind"] == "range"
    assert parsed["low"] == 200.0
    assert parsed["high"] == 300.0
    assert parsed["unit"] == "MPa"
    assert parsed["value"] is None


def test_parse_back_ascii_uncertainty() -> None:
    """The ASCII ``+/-`` spelling of uncertainty is accepted."""
    parsed = parse_back("10 +/- 2 mm")
    assert parsed["value"] == 10.0
    assert parsed["uncertainty"] == 2.0
    assert parsed["unit"] == "mm"


def test_round_trip() -> None:
    """format_measurement → parse_back preserves every part."""
    assert parse_back(format_measurement(148, "HV")) == {
        "kind": "value",
        "value": 148.0,
        "low": None,
        "high": None,
        "unit": "HV",
        "uncertainty": None,
    }
    assert parse_back(format_measurement(148, "HV", uncertainty=5))["uncertainty"] == 5.0
    range_back = parse_back(format_measurement((200, 300), "MPa"))
    assert (range_back["low"], range_back["high"]) == (200.0, 300.0)


def test_as_dict() -> None:
    """ParsedMeasurement.as_dict exposes every field including ``None``."""
    parsed = ParsedMeasurement(
        kind="value",
        value=7.0,
        low=None,
        high=None,
        unit=None,
        uncertainty=None,
    )
    assert parsed.as_dict() == {
        "kind": "value",
        "value": 7.0,
        "low": None,
        "high": None,
        "unit": None,
        "uncertainty": None,
    }


def test_bad_range_len() -> None:
    """A range with != 2 items is rejected."""
    with pytest.raises(ValueError):
        format_measurement((1, 2, 3), "MPa")


def test_parse_back_unparseable() -> None:
    """An unrecognizable string raises ValueError."""
    with pytest.raises(ValueError):
        parse_back("not a measurement")
