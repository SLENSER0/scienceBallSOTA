"""Tests for the §6.13 extraction merge/dedup + confidence fusion orchestrator."""

from __future__ import annotations

from kg_extractors.merge_extractions import fuse_confidence, merge_extractions
from kg_schema.extraction import (
    DocumentExtraction,
    EntityExtract,
    MeasurementExtract,
)


def _entity(
    text: str,
    *,
    canonical_name: str | None = None,
    confidence: float = 0.6,
    evidence_text: str = "span",
) -> EntityExtract:
    return EntityExtract(
        text=text,
        entity_type="Material",
        canonical_name=canonical_name,
        confidence=confidence,
        evidence_text=evidence_text,
    )


def _measurement(
    prop: str,
    *,
    value: float | None = None,
    unit: str | None = None,
    confidence: float = 0.6,
    evidence_text: str = "span",
) -> MeasurementExtract:
    return MeasurementExtract(
        property=prop,
        value=value,
        unit=unit,
        confidence=confidence,
        evidence_text=evidence_text,
    )


def test_fuse_confidence_hand_values() -> None:
    # noisy-OR: 1 - (1-0.6)(1-0.7) = 0.88
    assert fuse_confidence([0.6, 0.7]) == 0.88
    # 1 - 0.5^3 = 0.875
    assert fuse_confidence([0.5, 0.5, 0.5]) == 0.875
    # empty -> 0.0, single value passes through
    assert fuse_confidence([]) == 0.0
    assert fuse_confidence([0.42]) == 0.42


def test_same_entity_fused_noisy_or() -> None:
    a = DocumentExtraction(entities=[_entity("H2SO4", canonical_name="mat:h2so4", confidence=0.6)])
    b = DocumentExtraction(entities=[_entity("H2SO4", canonical_name="mat:h2so4", confidence=0.7)])
    merged = merge_extractions([a, b])
    assert len(merged.entities) == 1
    assert merged.entities[0].canonical_name == "mat:h2so4"
    assert merged.entities[0].confidence == 0.88


def test_distinct_entities_kept() -> None:
    a = DocumentExtraction(entities=[_entity("iron", canonical_name="mat:fe")])
    b = DocumentExtraction(entities=[_entity("copper", canonical_name="mat:cu")])
    merged = merge_extractions([a, b])
    assert len(merged.entities) == 2
    assert {e.canonical_name for e in merged.entities} == {"mat:fe", "mat:cu"}


def test_entities_dedup_by_lowercased_text_without_canonical() -> None:
    # No canonical_name -> key falls back to lowercased surface text.
    a = DocumentExtraction(entities=[_entity("Медь", confidence=0.6)])
    b = DocumentExtraction(entities=[_entity("медь", confidence=0.7)])
    merged = merge_extractions([a, b])
    assert len(merged.entities) == 1
    assert merged.entities[0].confidence == 0.88


def test_duplicate_measurements_fused() -> None:
    a = DocumentExtraction(
        measurements=[_measurement("tensile_strength", value=500.0, unit="MPa", confidence=0.6)]
    )
    b = DocumentExtraction(
        measurements=[_measurement("tensile_strength", value=500.0, unit="MPa", confidence=0.7)]
    )
    merged = merge_extractions([a, b])
    assert len(merged.measurements) == 1
    assert merged.measurements[0].confidence == 0.88


def test_different_measurements_kept() -> None:
    a = DocumentExtraction(measurements=[_measurement("tensile_strength", value=500.0, unit="MPa")])
    b = DocumentExtraction(measurements=[_measurement("tensile_strength", value=600.0, unit="MPa")])
    merged = merge_extractions([a, b])
    assert len(merged.measurements) == 2
    assert sorted(m.value for m in merged.measurements) == [500.0, 600.0]


def test_longest_evidence_text_retained() -> None:
    short = _measurement("hardness", value=200.0, unit="HV", confidence=0.6, evidence_text="HV 200")
    long = _measurement(
        "hardness",
        value=200.0,
        unit="HV",
        confidence=0.7,
        evidence_text="the measured hardness reached 200 HV after ageing",
    )
    merged = merge_extractions(
        [DocumentExtraction(measurements=[short]), DocumentExtraction(measurements=[long])]
    )
    assert len(merged.measurements) == 1
    assert merged.measurements[0].evidence_text == long.evidence_text
    assert merged.measurements[0].confidence == 0.88


def test_empty_list_returns_empty_extraction() -> None:
    merged = merge_extractions([])
    assert isinstance(merged, DocumentExtraction)
    assert merged.entities == []
    assert merged.measurements == []
    assert merged.relations == []
    assert merged.numeric_constraints == []
    assert merged.claims == []
    assert merged.regimes == []


def test_single_extraction_passthrough() -> None:
    doc = DocumentExtraction(
        entities=[
            _entity("iron", canonical_name="mat:fe", confidence=0.7),
            _entity("copper", canonical_name="mat:cu", confidence=0.6),
        ],
        measurements=[_measurement("tensile_strength", value=500.0, unit="MPa", confidence=0.6)],
    )
    merged = merge_extractions([doc])
    assert len(merged.entities) == 2
    assert {e.canonical_name for e in merged.entities} == {"mat:fe", "mat:cu"}
    # A single source value fuses to itself (passthrough).
    fe = next(e for e in merged.entities if e.canonical_name == "mat:fe")
    assert fe.confidence == 0.7
    assert len(merged.measurements) == 1
    assert merged.measurements[0].value == 500.0
