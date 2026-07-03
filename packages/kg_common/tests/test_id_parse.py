"""Tests for deterministic id parsing/validation (§3.8). / Тесты разбора id."""

from __future__ import annotations

from kg_common.id_parse import (
    ParsedId,
    is_uuid5_key,
    label_for_prefix,
    parse_id,
    validate_id,
)
from kg_common.ids import uuid5_id


def test_parse_slug_id() -> None:
    p = parse_id("material:al-cu-2024")
    assert p.prefix == "material"
    assert p.key == "al-cu-2024"
    assert p.is_uuid is False
    assert p.raw == "material:al-cu-2024"


def test_label_for_prefix_known() -> None:
    assert label_for_prefix("material") == "Material"
    assert label_for_prefix("ev") == "Evidence"


def test_label_for_prefix_unknown() -> None:
    assert label_for_prefix("zzz") is None


def test_validate_matching_label() -> None:
    assert validate_id("property:hardness", "Property") is True


def test_validate_wrong_label() -> None:
    assert validate_id("property:hardness", "Material") is False


def test_validate_no_colon() -> None:
    assert validate_id("nocolon") is False


def test_validate_no_expected_label() -> None:
    # Known prefix, no expected label -> valid on structure alone.
    assert validate_id("property:hardness") is True
    assert validate_id("zzz:whatever") is False
    # Empty key is invalid even with a known prefix.
    assert validate_id("material:") is False


def test_parse_uuid5_id_is_uuid() -> None:
    ident = uuid5_id("Evidence", "d", "s", "r")
    assert parse_id(ident).is_uuid is True


def test_parsed_id_as_dict() -> None:
    d = ParsedId("material:x", "material", "x", False).as_dict()
    assert d["prefix"] == "material"
    assert d == {
        "raw": "material:x",
        "prefix": "material",
        "key": "x",
        "is_uuid": False,
    }


def test_is_uuid5_key() -> None:
    ident = uuid5_id("Evidence", "d", "s", "r")
    _, key = ident.split(":", 1)
    assert is_uuid5_key(key) is True
    assert is_uuid5_key("al-cu-2024") is False
    assert is_uuid5_key("") is False


def test_parse_no_colon_yields_empty_prefix() -> None:
    p = parse_id("nocolon")
    assert p.prefix == ""
    assert p.key == "nocolon"
    assert p.is_uuid is False


def test_uuid_prefix_roundtrips_to_label() -> None:
    ident = uuid5_id("Evidence", "d", "s", "r")
    p = parse_id(ident)
    assert p.prefix == "ev"
    assert label_for_prefix(p.prefix) == "Evidence"
    assert validate_id(ident, "Evidence") is True
