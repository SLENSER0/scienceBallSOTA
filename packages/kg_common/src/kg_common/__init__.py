"""kg_common — shared config, DTOs, deterministic IDs, logging, telemetry."""

from __future__ import annotations

from kg_common.config import Settings, get_settings
from kg_common.dto import (
    AnswerPayload,
    ChatStreamEvent,
    Citation,
    EntityMention,
    EvidenceRef,
    GraphEdge,
    GraphNode,
    GraphResponse,
    RangeConstraint,
)
from kg_common.ids import (
    LABEL_TO_ID_PREFIX,
    canonical_key,
    evidence_id,
    make_id,
    regime_id,
    short_hash,
    slugify,
    uuid5_id,
)
from kg_common.logging import configure, get_logger
from kg_common.telemetry import setup_observability

__version__ = "0.1.0"

__all__ = [
    "LABEL_TO_ID_PREFIX",
    "AnswerPayload",
    "ChatStreamEvent",
    "Citation",
    "EntityMention",
    "EvidenceRef",
    "GraphEdge",
    "GraphNode",
    "GraphResponse",
    "RangeConstraint",
    "Settings",
    "canonical_key",
    "configure",
    "evidence_id",
    "get_logger",
    "get_settings",
    "make_id",
    "regime_id",
    "setup_observability",
    "short_hash",
    "slugify",
    "uuid5_id",
]
