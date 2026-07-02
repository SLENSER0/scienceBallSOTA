"""Ontology consistency tests (§3.4 / §3.5 / §3.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kg_common.ids import LABEL_TO_ID_PREFIX
from kg_schema import (
    EDGE_SCHEMA,
    ENTITY_LABELS,
    GapType,
    MeasurementExtract,
    NodeLabel,
    RelType,
    RunLabel,
    is_valid_edge,
)
from kg_schema.relationships import ENTITY


def test_core_labels_count() -> None:
    # 33 core labels from §8.1 must all be present.
    core = {
        "Document",
        "Paper",
        "Section",
        "Paragraph",
        "Table",
        "Figure",
        "Chunk",
        "Evidence",
        "Claim",
        "Finding",
        "Experiment",
        "Sample",
        "Material",
        "Alloy",
        "ChemicalElement",
        "Composition",
        "ProcessingRegime",
        "ProcessingStep",
        "Parameter",
        "Equipment",
        "Lab",
        "ResearchTeam",
        "Person",
        "Property",
        "Measurement",
        "Unit",
        "Method",
        "Dataset",
        "Project",
        "Decision",
        "CurationEvent",
        "Gap",
        "Contradiction",
    }
    labels = {str(x) for x in NodeLabel}
    assert core <= labels, core - labels
    assert len(core) == 33


def test_every_label_has_id_prefix() -> None:
    for label in NodeLabel:
        assert label in LABEL_TO_ID_PREFIX, f"{label} missing id prefix"


def test_gap_type_has_nine_core() -> None:
    core = {
        "missing_property_value",
        "missing_baseline",
        "missing_processing_parameter",
        "missing_equipment",
        "missing_unit",
        "unverified_claim",
        "contradictory_measurements",
        "low_coverage_material",
        "orphan_entity",
    }
    assert core <= {str(x) for x in GapType}


def test_edge_schema_labels_known() -> None:
    known = {str(x) for x in NodeLabel} | {str(x) for x in RunLabel} | {ENTITY}
    for f, r, t in EDGE_SCHEMA:
        assert f in known, f
        assert t in known, t
        assert r in {str(x) for x in RelType}, r


def test_every_reltype_used() -> None:
    used = {r for _, r, _ in EDGE_SCHEMA}
    for rel in RelType:
        assert rel in used, f"{rel} not in EDGE_SCHEMA"


def test_is_valid_edge() -> None:
    assert is_valid_edge("Chunk", "MENTIONS", "Material")  # Entity expansion
    assert is_valid_edge("Measurement", "OF_PROPERTY", "Property")
    assert is_valid_edge("Claim", "CONTRADICTS", "Claim")
    assert not is_valid_edge("Material", "CONTRADICTS", "Person")


def test_measurement_extract_validation() -> None:
    with pytest.raises(ValidationError):
        MeasurementExtract(property="hardness", confidence=1.5, evidence_text="x")
    with pytest.raises(ValidationError):
        MeasurementExtract(property="hardness", confidence=0.9, evidence_text="")
    ok = MeasurementExtract(
        property="recovery", value=92.0, unit="%", confidence=0.8, evidence_text="recovery of 92%"
    )
    assert ok.value == 92.0


def test_entity_super_label_subset() -> None:
    all_labels = {str(x) for x in NodeLabel}
    assert all_labels >= ENTITY_LABELS
