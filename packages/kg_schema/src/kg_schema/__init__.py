"""kg_schema — domain ontology: labels, relationships, enums, extraction models."""

from __future__ import annotations

from kg_schema.enums import (
    CONFIDENTIALITY_ORDER,
    Atmosphere,
    ConfidentialityLevel,
    CurationAction,
    CurationTargetType,
    EffectDirection,
    EvidenceStrength,
    GapType,
    MatchDecision,
    MaterialClass,
    MetallurgicalDomain,
    PracticeGeography,
    ProcessingOperation,
    PropertyClass,
    ReviewStatus,
    Role,
    SourceDocType,
    SourceType,
    VerificationLevel,
)
from kg_schema.extraction import (
    ClaimExtract,
    DocumentExtraction,
    EntityExtract,
    ExperimentExtract,
    MeasurementExtract,
    NumericConstraintExtract,
    ProcessingRegimeExtract,
    RelationExtract,
)
from kg_schema.labels import (
    ALL_LABELS,
    ENTITY_LABELS,
    FACTUAL_LABELS,
    NodeLabel,
    RunLabel,
)
from kg_schema.relationships import (
    EDGE_SCHEMA,
    FACTUAL_RELS,
    SYMMETRIC_RELS,
    RelType,
    is_valid_edge,
)

__version__ = "0.1.0"

__all__ = [
    # labels
    "NodeLabel",
    "RunLabel",
    "ENTITY_LABELS",
    "FACTUAL_LABELS",
    "ALL_LABELS",
    # relationships
    "RelType",
    "EDGE_SCHEMA",
    "SYMMETRIC_RELS",
    "FACTUAL_RELS",
    "is_valid_edge",
    # enums
    "GapType",
    "ReviewStatus",
    "SourceType",
    "EffectDirection",
    "MatchDecision",
    "CurationAction",
    "CurationTargetType",
    "MaterialClass",
    "PropertyClass",
    "ProcessingOperation",
    "Atmosphere",
    "MetallurgicalDomain",
    "PracticeGeography",
    "EvidenceStrength",
    "VerificationLevel",
    "SourceDocType",
    "Role",
    "ConfidentialityLevel",
    "CONFIDENTIALITY_ORDER",
    # extraction
    "EntityExtract",
    "NumericConstraintExtract",
    "MeasurementExtract",
    "ProcessingRegimeExtract",
    "RelationExtract",
    "ClaimExtract",
    "ExperimentExtract",
    "DocumentExtraction",
]
