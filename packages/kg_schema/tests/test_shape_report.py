"""Tests for the roll-up shape-conformance report (§24.19)."""

from __future__ import annotations

from typing import Any

from kg_schema.shape_report import (
    ShapeReport,
    ShapeViolationEntry,
    build_shape_report,
)


def _good_measurement() -> dict[str, Any]:
    """Полностью конформный Measurement / fully-conforming node (§3.6/§3.7)."""
    return {
        "label": "Measurement",
        "id": "measurement:m1",
        "name": "Cu recovery 92%",
        "extractor_run_id": "run:2026-07-03T10:00",
        "created_at": "2026-07-03T10:00:00Z",
        "confidence": 0.9,
        "review_status": "accepted",
        "evidence_strength": "peer_reviewed",
        "unit": "%",
        "normalized_unit": "percent",
        "value_normalized": 92.0,
    }


def _measurement_missing_provenance() -> dict[str, Any]:
    """Measurement без extractor_run_id / missing provenance (evidence-first)."""
    node = _good_measurement()
    node["id"] = "measurement:m2"
    del node["extractor_run_id"]
    return node


def _claim_bad_enum() -> dict[str, Any]:
    """Claim с недопустимым review_status / illegal controlled value."""
    return {
        "label": "Claim",
        "id": "claim:c1",
        "name": "Leaching improves yield",
        "extractor_run_id": "run:x",
        "created_at": "2026-07-03T10:00:00Z",
        "review_status": "maybe",  # not in {pending, accepted, rejected, corrected}
    }


def test_all_conformant_nodes() -> None:
    report = build_shape_report([_good_measurement()])
    assert isinstance(report, ShapeReport)
    assert report.total == 1
    assert report.conformant == 1
    assert report.nonconformant == 0
    assert report.violations == ()
    assert report.conforms is True


def test_violating_node_is_counted() -> None:
    report = build_shape_report([_good_measurement(), _measurement_missing_provenance()])
    assert report.total == 2
    assert report.conformant == 1
    assert report.nonconformant == 1
    assert report.conforms is False
    # Exactly one hard violation: the missing provenance field.
    assert len(report.violations) == 1
    entry = report.violations[0]
    assert isinstance(entry, ShapeViolationEntry)
    assert entry.index == 1
    assert entry.label == "Measurement"
    assert entry.field == "extractor_run_id"


def test_by_label_breakdown() -> None:
    report = build_shape_report(
        [
            _good_measurement(),
            _measurement_missing_provenance(),
            _claim_bad_enum(),
        ]
    )
    assert report.by_label == {
        "Measurement": {"total": 2, "conformant": 1},
        "Claim": {"total": 1, "conformant": 0},
    }


def test_violation_reasons_captured() -> None:
    report = build_shape_report([_claim_bad_enum()])
    assert report.total == 1
    assert report.conformant == 0
    assert len(report.violations) == 1
    entry = report.violations[0]
    assert entry.field == "review_status"
    assert "maybe" in entry.message
    assert entry.label == "Claim"
    assert entry.index == 0


def test_empty_input_zeros() -> None:
    report = build_shape_report([])
    assert report.total == 0
    assert report.conformant == 0
    assert report.nonconformant == 0
    assert report.violations == ()
    assert report.by_label == {}
    assert report.ratio == 0.0
    assert report.conforms is True


def test_conformance_ratio() -> None:
    report = build_shape_report(
        [
            _good_measurement(),
            _good_measurement(),
            _measurement_missing_provenance(),
            _claim_bad_enum(),
        ]
    )
    assert report.total == 4
    assert report.conformant == 2
    assert report.ratio == 0.5


def test_as_dict_shape() -> None:
    report = build_shape_report([_good_measurement(), _measurement_missing_provenance()])
    payload = report.as_dict()
    assert payload["total"] == 2
    assert payload["conformant"] == 1
    assert payload["nonconformant"] == 1
    assert payload["ratio"] == 0.5
    assert payload["conforms"] is False
    assert payload["by_label"] == {"Measurement": {"total": 2, "conformant": 1}}
    assert isinstance(payload["violations"], list)
    assert payload["violations"][0] == {
        "index": 1,
        "label": "Measurement",
        "field": "extractor_run_id",
        "message": payload["violations"][0]["message"],
    }
    assert "provenance" in payload["violations"][0]["message"]
