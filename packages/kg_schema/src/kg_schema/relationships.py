"""Relationship types + declarative edge schema (§3.5 / §8.2) + domain (§24.2)."""

from __future__ import annotations

from enum import StrEnum

from kg_schema.labels import ENTITY_LABELS, NodeLabel, RunLabel


class RelType(StrEnum):
    # -- document / chunk structure --
    HAS_SECTION = "HAS_SECTION"
    HAS_CHUNK = "HAS_CHUNK"
    MENTIONS = "MENTIONS"
    FROM_CHUNK = "FROM_CHUNK"
    FROM_TABLE = "FROM_TABLE"
    # -- evidence / claims --
    SUPPORTS = "SUPPORTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    EXTRACTED_BY = "EXTRACTED_BY"
    REPORTS = "REPORTS"
    CONTRADICTS = "CONTRADICTS"
    ABOUT = "ABOUT"
    DETECTED_BY = "DETECTED_BY"
    # -- experiment --
    USES_SAMPLE = "USES_SAMPLE"
    HAS_MATERIAL = "HAS_MATERIAL"
    HAS_COMPOSITION = "HAS_COMPOSITION"
    CONTAINS_ELEMENT = "CONTAINS_ELEMENT"
    PROCESSED_BY = "PROCESSED_BY"
    HAS_STEP = "HAS_STEP"
    HAS_PARAMETER = "HAS_PARAMETER"
    USED_EQUIPMENT = "USED_EQUIPMENT"
    PERFORMED_BY = "PERFORMED_BY"
    PART_OF = "PART_OF"
    MEMBER_OF = "MEMBER_OF"
    MEASURED = "MEASURED"
    OF_PROPERTY = "OF_PROPERTY"
    HAS_UNIT = "HAS_UNIT"
    # -- about / gap --
    ABOUT_MATERIAL = "ABOUT_MATERIAL"
    ABOUT_PROPERTY = "ABOUT_PROPERTY"
    ABOUT_REGIME = "ABOUT_REGIME"
    # -- curation --
    AFFECTS = "AFFECTS"
    CHANGED = "CHANGED"
    # -- domain (§24.2) --
    TREATS_WATER = "TREATS_WATER"
    REMOVES_CONTAMINANT = "REMOVES_CONTAMINANT"
    INJECTS_INTO_HORIZON = "INJECTS_INTO_HORIZON"
    CIRCULATES_ELECTROLYTE = "CIRCULATES_ELECTROLYTE"
    FEEDS_ELECTROLYTE_TO_CELL = "FEEDS_ELECTROLYTE_TO_CELL"
    OPERATES_IN_CLIMATE = "OPERATES_IN_CLIMATE"
    IMPLEMENTED_IN_COUNTRY = "IMPLEMENTED_IN_COUNTRY"
    HAS_TECHNOECONOMIC_INDICATOR = "HAS_TECHNOECONOMIC_INDICATOR"
    HAS_APPLICABILITY_CONDITION = "HAS_APPLICABILITY_CONDITION"
    HAS_LIMITATION = "HAS_LIMITATION"
    RECOMMENDS_SOLUTION = "RECOMMENDS_SOLUTION"
    COMPARES_WITH = "COMPARES_WITH"
    HAS_PRACTICE_TYPE = "HAS_PRACTICE_TYPE"
    DISTRIBUTES_BETWEEN = "DISTRIBUTES_BETWEEN"
    PARTITIONED_TO_PHASE = "PARTITIONED_TO_PHASE"
    HAS_DISTRIBUTION_COEFFICIENT = "HAS_DISTRIBUTION_COEFFICIENT"
    APPLIES_TO = "APPLIES_TO"
    IMPLEMENTED_IN = "IMPLEMENTED_IN"
    EXPERT_IN = "EXPERT_IN"
    LOCATED_IN = "LOCATED_IN"


# Virtual label meaning "any :Entity" in edge signatures.
ENTITY = "Entity"

# Declarative (from, rel, to) signatures (§3.5). ``Entity`` = any ENTITY_LABELS.
EdgeSig = tuple[str, str, str]
EDGE_SCHEMA: list[EdgeSig] = [
    # structure
    (NodeLabel.DOCUMENT, RelType.HAS_SECTION, NodeLabel.SECTION),
    (NodeLabel.DOCUMENT, RelType.HAS_CHUNK, NodeLabel.CHUNK),
    (NodeLabel.SECTION, RelType.HAS_CHUNK, NodeLabel.CHUNK),
    (NodeLabel.PAPER, RelType.HAS_SECTION, NodeLabel.SECTION),
    (NodeLabel.CHUNK, RelType.MENTIONS, ENTITY),
    (NodeLabel.EVIDENCE, RelType.FROM_CHUNK, NodeLabel.CHUNK),
    (NodeLabel.EVIDENCE, RelType.FROM_TABLE, NodeLabel.TABLE),
    (NodeLabel.DOCUMENT, RelType.HAS_SECTION, NodeLabel.TABLE),
    # evidence / claims
    (NodeLabel.EVIDENCE, RelType.SUPPORTS, NodeLabel.CLAIM),
    (NodeLabel.EVIDENCE, RelType.EXTRACTED_BY, RunLabel.EXTRACTOR_RUN),
    (NodeLabel.MEASUREMENT, RelType.SUPPORTED_BY, NodeLabel.EVIDENCE),
    (NodeLabel.CLAIM, RelType.SUPPORTED_BY, NodeLabel.EVIDENCE),
    (NodeLabel.FINDING, RelType.SUPPORTED_BY, NodeLabel.EVIDENCE),
    (NodeLabel.RECOMMENDATION, RelType.SUPPORTED_BY, NodeLabel.EVIDENCE),
    (NodeLabel.KNOWLEDGE_CLAIM, RelType.SUPPORTED_BY, NodeLabel.EVIDENCE),
    (NodeLabel.PAPER, RelType.REPORTS, NodeLabel.EXPERIMENT),
    (NodeLabel.DOCUMENT, RelType.REPORTS, NodeLabel.EXPERIMENT),
    (NodeLabel.CLAIM, RelType.CONTRADICTS, NodeLabel.CLAIM),
    (NodeLabel.KNOWLEDGE_CLAIM, RelType.CONTRADICTS, NodeLabel.KNOWLEDGE_CLAIM),
    # experiment
    (NodeLabel.EXPERIMENT, RelType.USES_SAMPLE, NodeLabel.SAMPLE),
    (NodeLabel.SAMPLE, RelType.HAS_MATERIAL, NodeLabel.MATERIAL),
    (NodeLabel.EXPERIMENT, RelType.HAS_MATERIAL, NodeLabel.MATERIAL),
    (NodeLabel.MATERIAL, RelType.HAS_COMPOSITION, NodeLabel.COMPOSITION),
    (NodeLabel.COMPOSITION, RelType.CONTAINS_ELEMENT, NodeLabel.CHEMICAL_ELEMENT),
    (NodeLabel.EXPERIMENT, RelType.PROCESSED_BY, NodeLabel.PROCESSING_REGIME),
    (NodeLabel.SAMPLE, RelType.PROCESSED_BY, NodeLabel.PROCESSING_REGIME),
    (NodeLabel.PROCESSING_REGIME, RelType.HAS_STEP, NodeLabel.PROCESSING_STEP),
    (NodeLabel.PROCESSING_REGIME, RelType.HAS_PARAMETER, NodeLabel.PARAMETER),
    (NodeLabel.PROCESSING_STEP, RelType.HAS_PARAMETER, NodeLabel.PARAMETER),
    (NodeLabel.EXPERIMENT, RelType.USED_EQUIPMENT, NodeLabel.EQUIPMENT),
    (NodeLabel.EXPERIMENT, RelType.PERFORMED_BY, NodeLabel.PERSON),
    (NodeLabel.EXPERIMENT, RelType.PERFORMED_BY, NodeLabel.LAB),
    (NodeLabel.PERSON, RelType.MEMBER_OF, NodeLabel.LAB),
    (NodeLabel.PERSON, RelType.MEMBER_OF, NodeLabel.RESEARCH_TEAM),
    (NodeLabel.LAB, RelType.PART_OF, NodeLabel.PROJECT),
    # measurement
    (NodeLabel.EXPERIMENT, RelType.MEASURED, NodeLabel.MEASUREMENT),
    (NodeLabel.SAMPLE, RelType.MEASURED, NodeLabel.MEASUREMENT),
    (NodeLabel.MEASUREMENT, RelType.OF_PROPERTY, NodeLabel.PROPERTY),
    (NodeLabel.MEASUREMENT, RelType.HAS_UNIT, NodeLabel.UNIT),
    # gaps / about
    (NodeLabel.GAP, RelType.ABOUT, ENTITY),
    (NodeLabel.GAP, RelType.ABOUT_MATERIAL, NodeLabel.MATERIAL),
    (NodeLabel.GAP, RelType.ABOUT_PROPERTY, NodeLabel.PROPERTY),
    (NodeLabel.GAP, RelType.ABOUT_REGIME, NodeLabel.PROCESSING_REGIME),
    (NodeLabel.GAP, RelType.DETECTED_BY, RunLabel.GAP_SCAN_RUN),
    (NodeLabel.CONTRADICTION, RelType.ABOUT, ENTITY),
    # curation
    (NodeLabel.DECISION, RelType.AFFECTS, ENTITY),
    (NodeLabel.CURATION_EVENT, RelType.CHANGED, ENTITY),
    # domain
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.TREATS_WATER, NodeLabel.MATERIAL),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.REMOVES_CONTAMINANT, NodeLabel.MATERIAL),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.INJECTS_INTO_HORIZON, NodeLabel.FACILITY),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.CIRCULATES_ELECTROLYTE, NodeLabel.MATERIAL),
    (NodeLabel.EQUIPMENT, RelType.FEEDS_ELECTROLYTE_TO_CELL, NodeLabel.EQUIPMENT),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.OPERATES_IN_CLIMATE, NodeLabel.GEOGRAPHY),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.IMPLEMENTED_IN_COUNTRY, NodeLabel.COUNTRY),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.IMPLEMENTED_IN, NodeLabel.FACILITY),
    (
        NodeLabel.TECHNOLOGY_SOLUTION,
        RelType.HAS_TECHNOECONOMIC_INDICATOR,
        NodeLabel.TECHNO_ECONOMIC_INDICATOR,
    ),
    (
        NodeLabel.TECHNOLOGY_SOLUTION,
        RelType.HAS_APPLICABILITY_CONDITION,
        NodeLabel.APPLICABILITY_CONDITION,
    ),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.HAS_LIMITATION, NodeLabel.LIMITATION),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.APPLIES_TO, NodeLabel.PROCESSING_REGIME),
    (NodeLabel.RECOMMENDATION, RelType.RECOMMENDS_SOLUTION, NodeLabel.TECHNOLOGY_SOLUTION),
    (NodeLabel.TECHNOLOGY_COMPARISON, RelType.COMPARES_WITH, NodeLabel.TECHNOLOGY_SOLUTION),
    (NodeLabel.TECHNOLOGY_SOLUTION, RelType.HAS_PRACTICE_TYPE, NodeLabel.GEOGRAPHY),
    (NodeLabel.MEASUREMENT, RelType.DISTRIBUTES_BETWEEN, NodeLabel.MATERIAL),
    (NodeLabel.MATERIAL, RelType.PARTITIONED_TO_PHASE, NodeLabel.MATERIAL),
    (NodeLabel.MEASUREMENT, RelType.HAS_DISTRIBUTION_COEFFICIENT, NodeLabel.PROPERTY),
    (NodeLabel.PERSON, RelType.EXPERT_IN, NodeLabel.PROCESSING_REGIME),
    (NodeLabel.PERSON, RelType.EXPERT_IN, NodeLabel.MATERIAL),
    (NodeLabel.LAB, RelType.EXPERT_IN, NodeLabel.PROCESSING_REGIME),
    (NodeLabel.FACILITY, RelType.LOCATED_IN, NodeLabel.COUNTRY),
    (NodeLabel.METHOD, RelType.APPLIES_TO, NodeLabel.MATERIAL),
    (NodeLabel.METHOD, RelType.REMOVES_CONTAMINANT, NodeLabel.MATERIAL),
]

# Symmetric edges: stored once, read both directions.
SYMMETRIC_RELS: frozenset[str] = frozenset({RelType.CONTRADICTS, RelType.COMPARES_WITH})

# Factual edges requiring provenance (§3.7).
FACTUAL_RELS: frozenset[str] = frozenset(
    {
        RelType.MEASURED,
        RelType.SUPPORTED_BY,
        RelType.ABOUT_MATERIAL,
        RelType.ABOUT_PROPERTY,
        RelType.ABOUT_REGIME,
        RelType.PROCESSED_BY,
        RelType.MENTIONS,
        RelType.OF_PROPERTY,
        RelType.REMOVES_CONTAMINANT,
        RelType.TREATS_WATER,
        RelType.DISTRIBUTES_BETWEEN,
        RelType.RECOMMENDS_SOLUTION,
    }
)


def _expand(label: str) -> set[str]:
    return set(ENTITY_LABELS) if label == ENTITY else {label}


def is_valid_edge(from_label: str, rel: str, to_label: str) -> bool:
    """True iff (from, rel, to) matches a declared signature (Entity expands)."""
    for f, r, t in EDGE_SCHEMA:
        if r != rel:
            continue
        if from_label in _expand(f) and to_label in _expand(t):
            return True
    return False
