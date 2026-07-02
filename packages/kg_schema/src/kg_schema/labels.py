"""Node labels catalog (§3.4 / §8.1) + domain extension (§24.2)."""

from __future__ import annotations

from enum import StrEnum


class NodeLabel(StrEnum):
    """The 33 core node labels (§8.1) plus domain labels (§24.2)."""

    # -- document structure --
    DOCUMENT = "Document"
    PAPER = "Paper"
    SECTION = "Section"
    PARAGRAPH = "Paragraph"
    TABLE = "Table"
    FIGURE = "Figure"
    CHUNK = "Chunk"
    # -- knowledge / provenance --
    EVIDENCE = "Evidence"
    CLAIM = "Claim"
    FINDING = "Finding"
    # -- experiment --
    EXPERIMENT = "Experiment"
    SAMPLE = "Sample"
    # -- materials --
    MATERIAL = "Material"
    ALLOY = "Alloy"
    CHEMICAL_ELEMENT = "ChemicalElement"
    COMPOSITION = "Composition"
    # -- process --
    PROCESSING_REGIME = "ProcessingRegime"
    PROCESSING_STEP = "ProcessingStep"
    PARAMETER = "Parameter"
    # -- equipment / people --
    EQUIPMENT = "Equipment"
    LAB = "Lab"
    RESEARCH_TEAM = "ResearchTeam"
    PERSON = "Person"
    # -- measurement --
    PROPERTY = "Property"
    MEASUREMENT = "Measurement"
    UNIT = "Unit"
    METHOD = "Method"
    DATASET = "Dataset"
    PROJECT = "Project"
    # -- curation / gaps --
    DECISION = "Decision"
    CURATION_EVENT = "CurationEvent"
    GAP = "Gap"
    CONTRADICTION = "Contradiction"

    # -- domain: mining-metallurgy (§24.2) --
    GEOGRAPHY = "Geography"
    COUNTRY = "Country"
    FACILITY = "Facility"
    TECHNOLOGY_SOLUTION = "TechnologySolution"
    RECOMMENDATION = "Recommendation"
    LIMITATION = "Limitation"
    APPLICABILITY_CONDITION = "ApplicabilityCondition"
    TECHNOLOGY_COMPARISON = "TechnologyComparison"
    KNOWLEDGE_CLAIM = "KnowledgeClaim"
    STANDARD = "Standard"
    TECHNO_ECONOMIC_INDICATOR = "TechnoEconomicIndicator"


class RunLabel(StrEnum):
    """Provenance run nodes (§8.2)."""

    EXTRACTOR_RUN = "ExtractorRun"
    GAP_SCAN_RUN = "GapScanRun"


# Super-label :Entity — all resolvable / embeddable entities (§3.4).
ENTITY_LABELS: frozenset[str] = frozenset(
    {
        NodeLabel.MATERIAL,
        NodeLabel.ALLOY,
        NodeLabel.PROPERTY,
        NodeLabel.EQUIPMENT,
        NodeLabel.LAB,
        NodeLabel.PERSON,
        NodeLabel.RESEARCH_TEAM,
        NodeLabel.PROCESSING_REGIME,
        NodeLabel.METHOD,
        NodeLabel.CHEMICAL_ELEMENT,
        NodeLabel.TECHNOLOGY_SOLUTION,
        NodeLabel.RECOMMENDATION,
        NodeLabel.FACILITY,
        NodeLabel.GEOGRAPHY,
    }
)

# Factual nodes that must carry evidence + provenance (§3.6 / §3.7).
FACTUAL_LABELS: frozenset[str] = frozenset(
    {
        NodeLabel.MEASUREMENT,
        NodeLabel.CLAIM,
        NodeLabel.FINDING,
        NodeLabel.RECOMMENDATION,
        NodeLabel.KNOWLEDGE_CLAIM,
        NodeLabel.CONTRADICTION,
    }
)

ALL_LABELS: frozenset[str] = frozenset(NodeLabel) | frozenset(RunLabel)
