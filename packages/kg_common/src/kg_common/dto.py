"""Shared Pydantic DTOs — the backend↔frontend contract (§5.3 / §7.3).

Field names use camelCase aliases so the JSON payload matches the TypeScript
types on the frontend, while Python code uses snake_case (``populate_by_name``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Subset of NodeLabel exposed to the graph payload (§5.3).
GraphNodeType = Literal[
    "Material",
    "Experiment",
    "ProcessingRegime",
    "Property",
    "Equipment",
    "Paper",
    "Claim",
    "Lab",
    "Person",
    "Gap",
    "Measurement",
    "Method",
    "TechnologySolution",
    "Recommendation",
    "Geography",
    "Contradiction",
    "Evidence",
    "Document",
]

ChatEventType = Literal[
    "token",
    "tool_start",
    "tool_end",
    "evidence",
    "graph",
    "table",
    "gap",
    "error",
    "done",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


def _to_camel(s: str) -> str:
    head, *tail = s.split("_")
    return head + "".join(w.capitalize() for w in tail)


class CamelModel(_CamelModel):
    """Base model that serializes snake_case fields as camelCase."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        alias_generator=_to_camel,
    )


class GraphNode(CamelModel):
    id: str
    label: str
    type: str
    confidence: float | None = None
    evidence_count: int | None = None
    verified: bool | None = None
    missing_fields: list[str] | None = None
    properties: dict[str, Any] | None = None
    community_id: int | None = None


class GraphEdge(CamelModel):
    id: str
    source: str
    target: str
    label: str
    type: str
    confidence: float | None = None
    evidence_count: int | None = None
    inferred: bool | None = None
    contradicted: bool | None = None
    evidence_ids: list[str] | None = None


class GraphResponse(CamelModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    layout_hints: dict[str, Any] | None = None
    query_context: dict[str, Any] | None = None


class EvidenceRef(CamelModel):
    """Points unambiguously at a source span (§7.3)."""

    evidence_id: str
    source_id: str
    doc_id: str | None = None
    page: int | None = None
    span_start: int | None = None
    span_end: int | None = None
    table_id: str | None = None
    row_index: int | None = None
    col_index: int | None = None
    text: str | None = None
    confidence: float = 1.0
    evidence_strength: str | None = None


class EntityMention(CamelModel):
    text: str
    canonical_id: str | None = None
    entity_type: str | None = None
    confidence: float = 1.0
    span_start: int | None = None
    span_end: int | None = None


class RangeConstraint(CamelModel):
    """Parsed numeric condition, e.g. ``сульфаты ≤300 мг/л`` (§24.4)."""

    parameter: str
    operator: Literal["<", "<=", ">", ">=", "=", "range", "approx"]
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    normalized_value: float | None = None
    normalized_min: float | None = None
    normalized_max: float | None = None
    normalized_unit: str | None = None
    source_span: str | None = None


class ChatStreamEvent(CamelModel):
    """One event in the agent's streamed response (§5.3)."""

    type: ChatEventType
    data: dict[str, Any] = Field(default_factory=dict)


class Citation(CamelModel):
    marker: str  # e.g. "[1]"
    evidence: EvidenceRef
    source_title: str | None = None
    year: int | None = None
    geography: str | None = None
    as_of: str | None = None  # date of actualization — when the source was ingested (§ верификация)


class AnswerPayload(CamelModel):
    """Structured agent answer returned by the API and used for export."""

    answer_markdown: str
    citations: list[Citation] = Field(default_factory=list)
    graph: GraphResponse | None = None
    table: dict[str, Any] | None = None
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    parsed_query: dict[str, Any] | None = None
    used_models: list[str] = Field(default_factory=list)
    verifier_report: dict[str, Any] | None = None
    # Chain-of-thought from reasoning-capable OSS models (DeepSeek-V4-Flash, GLM-5.2),
    # surfaced in the UI as a collapsible «thinking» panel. Empty for plain models.
    reasoning: str = ""
