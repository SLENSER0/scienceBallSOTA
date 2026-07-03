"""Tests for eLab/LIMS record → internal shape mapping (§20.5)."""

from __future__ import annotations

from kg_extractors.lab_record_map import (
    MappedRecord,
    Measurement,
    map_lab_record,
)


def test_maps_flat_fields() -> None:
    """A flat single-measurement record maps material + one measurement."""
    rec = {
        "material": "Ti-6Al-4V",
        "property": "hardness",
        "value": 340,
        "unit": "HV",
        "date": "2026-01-15",
    }
    out = map_lab_record(rec)
    assert out.material == "Ti-6Al-4V"
    assert len(out.measurements) == 1
    m = out.measurements[0]
    assert m.property == "hardness"
    assert m.value == 340
    assert m.unit == "HV"
    assert m.date == "2026-01-15"
    assert out.meta == {}


def test_missing_fields_tolerated() -> None:
    """Missing keys yield None, never an error; whitespace trims to None."""
    rec = {"material": "  Steel 45  ", "property": "yield_strength", "value": 355}
    out = map_lab_record(rec)
    assert out.material == "Steel 45"
    assert len(out.measurements) == 1
    m = out.measurements[0]
    assert m.property == "yield_strength"
    assert m.value == 355
    assert m.unit is None
    assert m.date is None


def test_measurements_list() -> None:
    """An explicit measurements list maps each item in order."""
    rec = {
        "material": "Al2O3",
        "measurements": [
            {"property": "density", "value": 3.95, "unit": "g/cm3"},
            {"property": "porosity", "value": 2.1, "unit": "%"},
            {},  # empty item is skipped
        ],
    }
    out = map_lab_record(rec)
    assert out.material == "Al2O3"
    assert len(out.measurements) == 2
    assert out.measurements[0].as_dict() == {
        "property": "density",
        "value": 3.95,
        "unit": "g/cm3",
        "date": None,
    }
    assert out.measurements[1].property == "porosity"
    assert out.measurements[1].unit == "%"


def test_meta_preserved() -> None:
    """Record keys not named by the mapping are preserved verbatim in meta."""
    rec = {
        "material": "Cu",
        "property": "conductivity",
        "value": 58.0,
        "unit": "MS/m",
        "operator": "Иванов И.И.",
        "lab_id": "ELN-7742",
        "temperature": 20,
    }
    out = map_lab_record(rec)
    assert out.meta == {
        "operator": "Иванов И.И.",
        "lab_id": "ELN-7742",
        "temperature": 20,
    }
    assert out.measurements[0].value == 58.0


def test_empty_record() -> None:
    """An empty record yields no material, no measurements, empty meta."""
    out = map_lab_record({})
    assert out.material is None
    assert out.measurements == ()
    assert out.meta == {}
    assert isinstance(out, MappedRecord)


def test_custom_mapping() -> None:
    """Custom mapping routes ELN-specific column names to internal fields."""
    rec = {
        "sample_name": "Inconel 718",
        "param": "tensile_strength",
        "reading": 1240,
        "units": "MPa",
        "measured_on": "2026-03-02",
        "notes": "batch B",
    }
    mapping = {
        "material": "sample_name",
        "property": "param",
        "value": "reading",
        "unit": "units",
        "date": "measured_on",
    }
    out = map_lab_record(rec, mapping)
    assert out.material == "Inconel 718"
    assert out.measurements[0].as_dict() == {
        "property": "tensile_strength",
        "value": 1240,
        "unit": "MPa",
        "date": "2026-03-02",
    }
    # unmapped ELN key survives in meta
    assert out.meta == {"notes": "batch B"}


def test_as_dict_roundtrip() -> None:
    """MappedRecord.as_dict renders the full nested internal shape."""
    rec = {
        "material": "SiC",
        "measurements": [{"property": "hardness", "value": 2800, "unit": "HV"}],
        "batch": "42",
    }
    out = map_lab_record(rec)
    assert out.as_dict() == {
        "material": "SiC",
        "measurements": [{"property": "hardness", "value": 2800, "unit": "HV", "date": None}],
        "meta": {"batch": "42"},
    }


def test_measurement_dataclass_as_dict() -> None:
    """Measurement.as_dict exposes all four fields including None."""
    m = Measurement(property="modulus", value=None, unit=None, date=None)
    assert m.as_dict() == {
        "property": "modulus",
        "value": None,
        "unit": None,
        "date": None,
    }
