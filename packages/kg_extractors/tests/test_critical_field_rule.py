"""Tests for rule ``missing_critical_field`` (§16.5)."""

from __future__ import annotations

from kg_extractors.critical_field_rule import (
    CRITICAL_FIELDS,
    MissingFieldFinding,
    detect_missing,
    scan,
)


def test_measurement_missing_one_field() -> None:
    node = {"id": "m1", "label": "Measurement", "value": 1, "unit": None, "property": "yield"}
    finding = detect_missing(node)
    assert finding is not None
    assert finding.missing_fields == ["unit"]
    assert finding.target_id == "m1"
    assert finding.label == "Measurement"


def test_fully_populated_measurement_is_none() -> None:
    node = {"id": "m2", "label": "Measurement", "value": 1, "unit": "MPa", "property": "yield"}
    assert detect_missing(node) is None


def test_unknown_label_is_none() -> None:
    node = {"id": "x1", "label": "Foo", "value": 1}
    assert detect_missing(node) is None


def test_missing_label_key_is_none() -> None:
    assert detect_missing({"id": "x2", "value": 1}) is None


def test_empty_string_counts_as_missing() -> None:
    node = {"id": "m3", "label": "Measurement", "value": 1, "unit": "MPa", "property": ""}
    finding = detect_missing(node)
    assert finding is not None
    assert finding.missing_fields == ["property"]


def test_blank_whitespace_string_counts_as_missing() -> None:
    node = {"id": "m4", "label": "Measurement", "value": 1, "unit": "  ", "property": "yield"}
    finding = detect_missing(node)
    assert finding is not None
    assert finding.missing_fields == ["unit"]


def test_processing_regime_missing_both() -> None:
    node = {"id": "p1", "label": "ProcessingRegime"}
    finding = detect_missing(node)
    assert finding is not None
    assert finding.missing_fields == ["temperature_c", "time_h"]


def test_processing_regime_fully_populated() -> None:
    node = {"id": "p2", "label": "ProcessingRegime", "temperature_c": 900, "time_h": 2.0}
    assert detect_missing(node) is None


def test_experiment_missing_material() -> None:
    node = {"id": "e1", "label": "Experiment", "material": None, "property": "hardness"}
    finding = detect_missing(node)
    assert finding is not None
    assert finding.missing_fields == ["material"]


def test_scan_returns_finding_per_defective_node() -> None:
    nodes = [
        {"id": "m1", "label": "Measurement", "value": 1, "unit": "MPa", "property": "yield"},
        {"id": "m2", "label": "Measurement", "value": 1, "unit": None, "property": "yield"},
        {"id": "p1", "label": "ProcessingRegime"},
    ]
    findings = scan(nodes)
    assert len(findings) == 2
    assert {f.target_id for f in findings} == {"m2", "p1"}


def test_custom_config_overrides_defaults() -> None:
    config = {"Widget": ["serial"]}
    node = {"id": "w1", "label": "Widget", "serial": None}
    finding = detect_missing(node, config)
    assert finding is not None
    assert finding.missing_fields == ["serial"]
    # Default Measurement fields no longer apply under the custom config.
    measurement = {"id": "m1", "label": "Measurement", "value": 1}
    assert detect_missing(measurement, config) is None


def test_custom_config_known_label_all_present_is_none() -> None:
    config = {"Widget": ["serial"]}
    assert detect_missing({"id": "w2", "label": "Widget", "serial": "abc"}, config) is None


def test_as_dict_missing_fields_is_list() -> None:
    node = {"id": "m1", "label": "Measurement", "value": 1, "unit": None, "property": "yield"}
    finding = detect_missing(node)
    assert finding is not None
    d = finding.as_dict()
    assert isinstance(d["missing_fields"], list)
    assert d == {"target_id": "m1", "label": "Measurement", "missing_fields": ["unit"]}


def test_finding_is_frozen() -> None:
    finding = MissingFieldFinding(target_id="m1", label="Measurement", missing_fields=["unit"])
    try:
        finding.target_id = "m2"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("MissingFieldFinding must be frozen")


def test_critical_fields_catalog_shape() -> None:
    assert CRITICAL_FIELDS["Measurement"] == ["value", "unit", "property"]
    assert CRITICAL_FIELDS["ProcessingRegime"] == ["temperature_c", "time_h"]
    assert CRITICAL_FIELDS["Experiment"] == ["material", "property"]
