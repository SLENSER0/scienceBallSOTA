"""Measurement normalizer → NormalizedMeasurement (§7.5).

Hand-checked values: current density ``А/м2`` → ``A/m^2`` (250 unchanged),
``мА/см2`` → ``A/m^2`` (×10: 250 → 2500), Vickers hardness bounds in HV.
"""

from __future__ import annotations

from kg_extractors.measurement_normalizer import (
    NormalizedMeasurement,
    normalize_measurement,
)


def test_current_density_normalized_unit() -> None:
    """250 А/м² → canonical A/m^2, value preserved, no flags (§7.5)."""
    m = normalize_measurement(250, "А/м2")
    assert m.normalized_unit == "A/m^2"
    assert m.value_normalized == 250.0
    assert m.value == 250.0
    assert m.flags == []
    assert m.review_needed is False
    assert m.in_range is True


def test_hardness_out_of_range_flag() -> None:
    """5000 HV exceeds the 2000 HV physical max → out_of_range + review (§7.7)."""
    m = normalize_measurement(5000, "HV", property_id="prop:hardness")
    assert "out_of_range" in m.flags
    assert m.in_range is False
    assert m.review_needed is True
    # HV is pint-inconvertible → raw value kept as canonical.
    assert m.value_normalized == 5000.0
    assert m.normalized_unit == "HV"
    # HV is a permitted hardness unit, so no unit flag.
    assert "unit_not_allowed" not in m.flags


def test_hardness_valid_in_range() -> None:
    """145 HV sits inside the typical band → in_range, no flags (§7.7)."""
    m = normalize_measurement(145, "HV", property_id="prop:hardness")
    assert m.in_range is True
    assert m.flags == []
    assert m.review_needed is False
    assert m.value_normalized == 145.0


def test_missing_unit_flag() -> None:
    """No unit → missing_unit flag + review, value still numeric (§7.5)."""
    m = normalize_measurement(250, None)
    assert "missing_unit" in m.flags
    assert m.review_needed is True
    assert m.unit is None
    assert m.normalized_unit is None
    assert m.value_normalized == 250.0


def test_disallowed_unit_flag() -> None:
    """V is not a current-density unit → unit_not_allowed, but 5 stays in range."""
    m = normalize_measurement(5, "V", property_id="prop:current_density")
    assert "unit_not_allowed" in m.flags
    assert "out_of_range" not in m.flags
    assert m.in_range is True
    assert m.review_needed is True


def test_ma_per_cm2_converts_to_a_per_m2() -> None:
    """250 мА/см² = 2500 A/m^2 (1 mA/cm² = 10 A/m²), hand-checked (§7.5)."""
    m = normalize_measurement(250, "мА/см2")
    assert m.normalized_unit == "A/m^2"
    assert m.value_normalized == 2500.0


def test_to_neo4j_props_columns() -> None:
    """to_neo4j_props emits the DB columns for a valid measurement (§7.5)."""
    m = normalize_measurement(250, "A/m^2", property_id="prop:current_density")
    props = m.to_neo4j_props()
    assert set(props) == {
        "property_id",
        "value_raw",
        "value",
        "unit",
        "value_normalized",
        "normalized_unit",
        "in_range",
        "flags",
        "review_needed",
    }
    assert props["property_id"] == "prop:current_density"
    assert props["value_normalized"] == 250.0
    assert props["normalized_unit"] == "A/m^2"
    assert props["flags"] == []
    assert props["review_needed"] is False
    assert props["in_range"] is True


def test_to_neo4j_props_drops_none_columns() -> None:
    """Missing-unit measurement omits null unit columns for Neo4j (§7.5)."""
    props = normalize_measurement(250, None).to_neo4j_props()
    assert "unit" not in props
    assert "normalized_unit" not in props
    assert "property_id" not in props
    assert props["flags"] == ["missing_unit"]
    assert props["value"] == 250.0


def test_unknown_property_still_normalizes() -> None:
    """Unknown property: units normalize, policy stays silent (graceful) (§7.5)."""
    m = normalize_measurement(250, "А/м2", property_id="prop:no_such_property")
    assert m.normalized_unit == "A/m^2"
    assert m.value_normalized == 250.0
    assert m.flags == []
    assert m.review_needed is False
    assert m.in_range is True


def test_ph_unitless_missing_unit_ok() -> None:
    """pH is unitless → a missing unit is legitimate, no flag raised (§7.2)."""
    m = normalize_measurement(7.0, None, property_id="prop:ph")
    assert m.flags == []
    assert m.review_needed is False
    assert m.in_range is True


def test_as_dict_has_all_fields() -> None:
    """as_dict() exposes the full NormalizedMeasurement field set (§7.5)."""
    m = normalize_measurement(145, "HV", property_id="prop:hardness")
    d = m.as_dict()
    assert set(d) == {
        "property_id",
        "value_raw",
        "value",
        "unit",
        "value_normalized",
        "normalized_unit",
        "in_range",
        "flags",
        "review_needed",
    }
    assert isinstance(m, NormalizedMeasurement)
    assert d["property_id"] == "prop:hardness"
    assert d["unit"] == "HV"
