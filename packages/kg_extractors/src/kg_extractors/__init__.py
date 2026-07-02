"""Rule + LLM + materials extractors, unit normalization, entity resolution."""

from __future__ import annotations

from kg_extractors.entity_resolution import EntityResolver, ResolvedEntity, get_resolver
from kg_extractors.llm import LLMClient, get_llm, is_oss_model
from kg_extractors.query_parser import QueryIntent, parse_query, scan_taxonomy
from kg_extractors.units import (
    Normalized,
    ParsedConstraint,
    parse_numeric_constraints,
    to_canonical,
)

__version__ = "0.1.0"

__all__ = [
    "parse_numeric_constraints",
    "to_canonical",
    "ParsedConstraint",
    "Normalized",
    "EntityResolver",
    "ResolvedEntity",
    "get_resolver",
    "parse_query",
    "scan_taxonomy",
    "QueryIntent",
    "LLMClient",
    "get_llm",
    "is_oss_model",
]
