"""SHACL-style shape validation for FAIR export (§24.19)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from kg_schema.shapes import (
    PROVENANCE_FIELDS,
    SHAPES,
    known_labels,
    validate_node,
    validate_nodes,
)


def _good_measurement() -> dict[str, Any]:
    """A fully-conforming Measurement carrying provenance (§3.6/§3.7)."""
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


def _severities(result: dict[str, Any]) -> set[str]:
    return {v["severity"] for v in result["violations"]}


def test_conforming_measurement_passes() -> None:
    result = validate_node(_good_measurement())
    # Every required + recommended field is present and vocab values are legal,
    # so there must be zero issues of any kind and it conforms.
    assert result["conforms"] is True
    assert result["violations"] == []


def test_measurement_missing_provenance_is_evidence_first_violation() -> None:
    node = _good_measurement()
    del node["extractor_run_id"]
    result = validate_node(node)
    assert result["conforms"] is False
    prov = [v for v in result["violations"] if v["field"] == "extractor_run_id"]
    assert len(prov) == 1
    assert prov[0]["severity"] == "violation"
    assert "evidence-first" in prov[0]["message"]
    assert "extractor_run_id" in PROVENANCE_FIELDS


def test_unknown_label_is_graceful() -> None:
    result = validate_node({"label": "Banana", "id": "x"})
    # Unmodelled labels never hard-fail: conforms stays True and the only note
    # is an informational skip on the label itself.
    assert result["conforms"] is True
    assert _severities(result) == {"info"}
    assert result["violations"][0]["field"] == "label"
    assert "Banana" not in known_labels()


def test_bad_evidence_strength_is_flagged() -> None:
    node = _good_measurement()
    node["evidence_strength"] = "rock_solid"  # not a permissible EvidenceStrength
    result = validate_node(node)
    assert result["conforms"] is False
    bad = [v for v in result["violations"] if v["field"] == "evidence_strength"]
    assert len(bad) == 1
    assert bad[0]["severity"] == "violation"
    assert "rock_solid" in bad[0]["message"]


def test_missing_recommended_is_warning_not_violation() -> None:
    # Required + provenance present, but every recommended field omitted.
    node = {
        "label": "Measurement",
        "id": "measurement:m2",
        "name": "bare measurement",
        "extractor_run_id": "run:1",
        "created_at": "2026-07-03T00:00:00Z",
    }
    result = validate_node(node)
    # Warnings do not break conformance.
    assert result["conforms"] is True
    assert _severities(result) == {"warning"}
    warned = {v["field"] for v in result["violations"]}
    assert warned == {
        "confidence",
        "review_status",
        "evidence_strength",
        "unit",
        "normalized_unit",
        "value_normalized",
    }


def test_evidence_requires_source_span_and_provenance() -> None:
    result = validate_node({"label": "Evidence", "id": "evidence:e1"})
    assert result["conforms"] is False
    violations = {v["field"]: v for v in result["violations"] if v["severity"] == "violation"}
    # doc_id + text (source span) and both provenance fields are required.
    assert set(violations) == {"doc_id", "text", "extractor_run_id", "created_at"}
    assert "evidence-first" in violations["created_at"]["message"]


def test_validate_nodes_aggregates() -> None:
    nodes = [
        _good_measurement(),  # conforms
        {  # missing provenance -> nonconforming
            "label": "Measurement",
            "id": "measurement:bad",
            "name": "no provenance",
        },
        {"label": "Banana", "id": "u1"},  # unknown -> conforms (info only)
    ]
    report = validate_nodes(nodes)
    assert report["total"] == 3
    assert report["conforming"] == 2
    assert report["nonconforming"] == 1
    assert report["conforms"] is False
    # The bad Measurement lacks extractor_run_id + created_at -> 2 violations.
    assert report["by_severity"]["violation"] == 2
    assert report["by_severity"]["info"] == 1
    assert report["nonconforming_by_label"] == {"Measurement": 1}
    assert len(report["results"]) == 3


def test_catalog_matches_resources_data_module() -> None:
    """The kg_schema SHAPES and the resources/shapes.py literal are identical."""
    repo_root = Path(__file__).resolve().parents[3]
    catalog_path = repo_root / "resources" / "shapes.py"
    assert catalog_path.is_file(), catalog_path
    spec = importlib.util.spec_from_file_location("_shapes_catalog", catalog_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SHAPES == SHAPES
    # Spot-check a known value survived the round-trip.
    assert SHAPES["Measurement"]["required"] == ["id", "name", "extractor_run_id", "created_at"]
