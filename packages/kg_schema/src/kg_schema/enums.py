"""Controlled vocabularies / enums for the domain ontology (§3.2 / §8.3 / §24).

All enums are ``StrEnum`` so they serialize as their string value in JSON and
Cypher and can be compared directly to strings.
"""

from __future__ import annotations

from enum import StrEnum


class GapType(StrEnum):
    """The 11 canonical gap types (§11.1/§15.1), reconciled with §7.4 (§3.5)."""

    MISSING_PROPERTY_VALUE = "missing_property_value"
    MISSING_BASELINE = "missing_baseline"
    MISSING_PROCESSING_PARAMETER = "missing_processing_parameter"
    MISSING_EQUIPMENT = "missing_equipment"
    MISSING_UNIT = "missing_unit"
    MISSING_SOURCE_SPAN = "missing_source_span"
    UNVERIFIED_CLAIM = "unverified_claim"
    CONTRADICTORY_MEASUREMENTS = "contradictory_measurements"
    LOW_COVERAGE_MATERIAL = "low_coverage_material"
    LOW_CONFIDENCE_ENTITY_RESOLUTION = "low_confidence_entity_resolution"
    ORPHAN_ENTITY = "orphan_entity"
    # domain gaps (§24.10 / §24.7)
    MISSING_GEOGRAPHY = "missing_geography"
    MISSING_APPLICABILITY_CONDITION = "missing_applicability_condition"
    MISSING_TECHNOECONOMIC = "missing_technoeconomic"
    ONLY_FOREIGN_SOURCES = "only_foreign_sources"
    NO_PILOT_DATA = "no_pilot_data"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class SourceType(StrEnum):
    """Where an Evidence span comes from (§8.3)."""

    PARAGRAPH = "paragraph"
    TABLE_CELL = "table_cell"
    FIGURE_CAPTION = "figure_caption"
    METADATA = "metadata"
    MANUAL = "manual"


class EffectDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NO_CHANGE = "no_change"


class MatchDecision(StrEnum):
    AUTO_MERGE = "auto_merge"
    REVIEW_NEEDED = "review_needed"
    SEPARATE = "separate"


class CurationAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    CORRECT = "correct"
    MERGE = "merge"
    SPLIT = "split"
    ALIAS_ADD = "alias_add"
    SCHEMA_CHANGE = "schema_change"
    # domain actions (§24.20)
    MARK_AS_DOMESTIC_PRACTICE = "mark_as_domestic_practice"
    MARK_AS_FOREIGN_PRACTICE = "mark_as_foreign_practice"
    SET_APPLICABILITY_CONDITION = "set_applicability_condition"
    ADD_LIMITATION = "add_limitation"
    RESOLVE_CONTRADICTION = "resolve_contradiction"
    ANNOTATE_GAP = "annotate_gap"


class CurationTargetType(StrEnum):
    NODE = "node"
    EDGE = "edge"
    EVIDENCE = "evidence"
    SCHEMA = "schema"


class MaterialClass(StrEnum):
    ORE = "ore"
    CONCENTRATE = "concentrate"
    MATTE = "matte"
    SLAG = "slag"
    TAILINGS = "tailings"
    METAL = "metal"
    ALLOY = "alloy"
    SOLUTION = "solution"
    ELECTROLYTE = "electrolyte"
    GAS = "gas"
    WATER = "water"
    WASTE = "waste"
    REAGENT = "reagent"
    OTHER = "other"


class PropertyClass(StrEnum):
    CONCENTRATION = "concentration"
    TEMPERATURE = "temperature"
    FLOW = "flow"
    ELECTROCHEMICAL = "electrochemical"
    MECHANICAL = "mechanical"
    RECOVERY = "recovery"
    EFFICIENCY = "efficiency"
    ECONOMIC = "economic"
    ENERGY = "energy"
    PHYSICOCHEMICAL = "physicochemical"
    OTHER = "other"


class ProcessingOperation(StrEnum):
    LEACHING = "leaching"
    HEAP_LEACHING = "heap_leaching"
    BIOLEACHING = "bioleaching"
    FLOTATION = "flotation"
    ELECTROWINNING = "electrowinning"
    ELECTROREFINING = "electrorefining"
    FLASH_SMELTING = "flash_smelting"
    FLUIDIZED_BED = "fluidized_bed"
    SMELTING = "smelting"
    CONVERTING = "converting"
    ROASTING = "roasting"
    DESALINATION = "desalination"
    REVERSE_OSMOSIS = "reverse_osmosis"
    ION_EXCHANGE = "ion_exchange"
    ELECTRODIALYSIS = "electrodialysis"
    NANOFILTRATION = "nanofiltration"
    LIME_SOFTENING = "lime_softening"
    GAS_CLEANING = "gas_cleaning"
    SO2_REMOVAL = "so2_removal"
    WATER_INJECTION = "water_injection"
    AGING = "aging"
    ANNEALING = "annealing"
    OTHER = "other"


class Atmosphere(StrEnum):
    AIR = "air"
    INERT = "inert"
    VACUUM = "vacuum"
    REDUCING = "reducing"
    OXIDIZING = "oxidizing"
    OTHER = "other"


class MetallurgicalDomain(StrEnum):
    HYDROMETALLURGY = "hydrometallurgy"
    PYROMETALLURGY = "pyrometallurgy"
    ENVIRONMENT = "environment"
    WATER_TREATMENT = "water_treatment"
    WASTE_PROCESSING = "waste_processing"
    MINERAL_PROCESSING = "mineral_processing"
    ELECTROMETALLURGY = "electrometallurgy"


class PracticeGeography(StrEnum):
    RUSSIA = "russia"
    CIS = "cis"
    FOREIGN = "foreign"
    GLOBAL = "global"
    UNKNOWN = "unknown"


class EvidenceStrength(StrEnum):
    PEER_REVIEWED = "peer_reviewed"
    PATENT = "patent"
    INTERNAL_REPORT = "internal_report"
    EXPERIMENT_PROTOCOL = "experiment_protocol"
    STANDARD = "standard"
    EXPERT_COMMENT = "expert_comment"
    UNVERIFIED = "unverified"


class VerificationLevel(StrEnum):
    """Confidence scale for claims/recommendations (§24.7)."""

    CONFIRMED = "confirmed"
    LIKELY = "likely"
    CONFLICTING = "conflicting"
    WEAKLY_SUPPORTED = "weakly_supported"
    UNVERIFIED = "unverified"
    OBSOLETE = "obsolete"


class SourceDocType(StrEnum):
    INTERNAL_REPORT = "internal_report"
    ARTICLE = "article"
    REVIEW = "review"
    PATENT = "patent"
    THESIS = "thesis"
    STANDARD = "standard"
    EXPERIMENT_PROTOCOL = "experiment_protocol"
    PRESENTATION = "presentation"
    CONFERENCE = "conference"
    HANDBOOK = "handbook"
    OTHER = "other"


class Role(StrEnum):
    """RBAC roles (§19 / §24.14)."""

    RESEARCHER = "researcher"
    ANALYST = "analyst"
    PROJECT_MANAGER = "project_manager"
    ADMIN = "admin"
    EXTERNAL_PARTNER = "external_partner"
    CURATOR = "curator"


class ConfidentialityLevel(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    COMMERCIAL_SECRET = "commercial_secret"
    PARTNER_VISIBLE = "partner_visible"


# Ordering used for access checks (higher index = more sensitive).
CONFIDENTIALITY_ORDER: list[str] = [
    ConfidentialityLevel.PUBLIC,
    ConfidentialityLevel.PARTNER_VISIBLE,
    ConfidentialityLevel.INTERNAL,
    ConfidentialityLevel.RESTRICTED,
    ConfidentialityLevel.COMMERCIAL_SECRET,
]
