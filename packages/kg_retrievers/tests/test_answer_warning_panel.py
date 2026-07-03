"""Tests for the chat answer warning panel (§15.9 / §5.2.2)."""

from __future__ import annotations

from kg_retrievers.answer_warning_panel import (
    MISSING_DATA_TYPES,
    WarningPanel,
    build_warning_panel,
)


def test_missing_data_types_membership() -> None:
    # missing_* families are in; low_coverage_material is a distinct family. / Разделение.
    assert "missing_unit" in MISSING_DATA_TYPES
    assert "missing_property_value" in MISSING_DATA_TYPES
    assert "low_coverage_material" not in MISSING_DATA_TYPES
    assert "contradictory_measurements" not in MISSING_DATA_TYPES


def test_all_empty_inputs() -> None:
    panel = build_warning_panel([], [], [])
    assert isinstance(panel, WarningPanel)
    assert panel.has_warnings is False
    assert panel.severity == "none"
    assert panel.contradiction_count == 0
    assert panel.low_confidence_count == 0
    assert panel.missing_data_count == 0
    assert panel.items == ()


def test_single_contradiction() -> None:
    panel = build_warning_panel([{"id": "c1"}], [], [])
    assert panel.contradiction_count == 1
    assert panel.has_warnings is True
    assert panel.severity == "high"


def test_low_confidence_threshold() -> None:
    nodes = [{"id": "n1", "confidence": 0.3}, {"id": "n2", "confidence": 0.8}]
    panel = build_warning_panel([], nodes, [], confidence_threshold=0.5)
    assert panel.low_confidence_count == 1
    assert panel.items[0]["id"] == "n1"


def test_gap_type_filtering() -> None:
    gaps = [
        {"id": "g1", "gap_type": "low_coverage_material"},
        {"id": "g2", "gap_type": "missing_unit"},
    ]
    panel = build_warning_panel([], [], gaps)
    # low_coverage_material is NOT missing-data; missing_unit IS. / Только пропуски.
    assert panel.missing_data_count == 1
    assert panel.items[0]["id"] == "g2"


def test_critical_gap_forces_critical_severity() -> None:
    gaps = [{"id": "g1", "gap_type": "missing_unit", "severity": "critical"}]
    panel = build_warning_panel([], [], gaps)
    assert panel.severity == "critical"
    assert panel.has_warnings is True


def test_items_length_equals_sum_of_counts_and_order() -> None:
    contradictions = [{"id": "c1"}]
    nodes = [{"id": "n1", "confidence": 0.1}, {"id": "n2", "confidence": 0.9}]
    gaps = [
        {"id": "g1", "gap_type": "missing_unit"},
        {"id": "g2", "gap_type": "missing_geography"},
        {"id": "g3", "gap_type": "low_coverage_material"},
    ]
    panel = build_warning_panel(contradictions, nodes, gaps)
    total = panel.contradiction_count + panel.missing_data_count + panel.low_confidence_count
    assert len(panel.items) == total
    assert total == 1 + 2 + 1
    # Order: contradictions -> missing-data -> low-confidence. / Порядок.
    assert [it["id"] for it in panel.items] == ["c1", "g1", "g2", "n1"]


def test_as_dict_exposes_flags() -> None:
    panel = build_warning_panel([{"id": "c1", "severity": "critical"}], [], [])
    d = panel.as_dict()
    assert d["has_warnings"] is True
    assert d["severity"] == "critical"
    assert d["contradiction_count"] == 1
    assert isinstance(d["items"], list)
