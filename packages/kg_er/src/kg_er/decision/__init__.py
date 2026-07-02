"""ER decision engine + property vocabulary mapping (§8.6/§8.7)."""

from __future__ import annotations

from kg_er.decision.engine import (
    MergeProposal,
    build_proposals,
    decide,
    thresholds_for,
)
from kg_er.decision.property_mapper import PropertyMapper, PropertyMapping

__all__ = [
    "decide",
    "thresholds_for",
    "MergeProposal",
    "build_proposals",
    "PropertyMapper",
    "PropertyMapping",
]
