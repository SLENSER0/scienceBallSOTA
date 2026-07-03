"""Tests for eLabFTW ``extra_fields`` metadata parsing (§20.4)."""

from __future__ import annotations

from ingestion_service.elabftw_metadata import (
    ElabField,
    ElabMetadata,
    extract_domain,
    parse_extra_fields,
)

_SAMPLE = {
    "extra_fields": {
        "Material": {"value": "AA2024"},
        "Temperature": {"value": "850", "unit": "C"},
        "Atmosphere": {"value": "Ar"},
    }
}


def test_parse_extra_fields_returns_three() -> None:
    fields = parse_extra_fields(_SAMPLE)
    assert len(fields) == 3
    assert all(isinstance(f, ElabField) for f in fields)
    by_name = {f.name: f for f in fields}
    assert by_name["Temperature"].value == "850"
    assert by_name["Temperature"].unit == "C"


def test_parse_extra_fields_empty() -> None:
    assert parse_extra_fields({}) == []
    assert parse_extra_fields({"extra_fields": {}}) == []


def test_extract_domain_material_and_temperature() -> None:
    meta = extract_domain(parse_extra_fields(_SAMPLE))
    assert meta.material == "AA2024"
    assert meta.temperature_c == 850.0
    assert meta.atmosphere == "Ar"
    assert meta.time_h is None
    assert len(meta.fields) == 3


def test_extract_domain_case_insensitive_and_aliases() -> None:
    fields = [
        ElabField(name="ALLOY", value="Ti-6Al-4V"),
        ElabField(name="time", value="2.5", unit="h"),
        ElabField(name="Equipment", value="MTS-810"),
    ]
    meta = extract_domain(fields)
    assert meta.material == "Ti-6Al-4V"
    assert meta.time_h == 2.5
    assert meta.equipment == "MTS-810"


def test_extract_domain_property() -> None:
    fields = [
        ElabField(name="property", value="120", unit="HV"),
    ]
    meta = extract_domain(fields)
    assert meta.measured_property != ""
    assert meta.measured_property == "120"
    assert meta.measured_value == 120.0
    assert meta.measured_unit == "HV"


def test_temperature_decimal_comma() -> None:
    fields = [ElabField(name="Temperature", value="20,5", unit="C")]
    meta = extract_domain(fields)
    assert meta.temperature_c == 20.5


def test_field_as_dict() -> None:
    d = ElabField(name="Material", value="AA2024").as_dict()
    assert d == {"name": "Material", "value": "AA2024", "unit": "", "group": ""}


def test_metadata_as_dict_contains_temperature_c() -> None:
    meta = extract_domain(parse_extra_fields(_SAMPLE))
    d = meta.as_dict()
    assert "temperature_c" in d
    assert d["temperature_c"] == 850.0
    assert isinstance(d["fields"], list)
    assert d["fields"][0]["name"] == "Material"


def test_empty_metadata_yields_empty_domain() -> None:
    meta = extract_domain(parse_extra_fields({}))
    assert isinstance(meta, ElabMetadata)
    assert meta.material == ""
    assert meta.temperature_c is None
    assert meta.fields == ()
