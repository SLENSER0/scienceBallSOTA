"""Graph-payload schema validation + DTO helpers (§3.16).

The graph-service ``/graph/schema`` endpoint publishes the label + relationship
catalog so a frontend client can validate a :class:`GraphResponse` (граф-ответ)
before it renders it. This module is the shared, HTTP-free core of that
endpoint:

- :func:`validate_graph_response` — parse an untrusted ``payload`` dict into a
  :class:`GraphResponse` and check that every node type (метка узла) is a known
  :class:`NodeLabel`, every edge type (тип связи) is a known :class:`RelType`,
  and every edge ``source`` / ``target`` references a node id in the payload;
- :func:`build_schema_descriptor` — the catalog itself (labels + relationship
  signatures) that ``/graph/schema`` exposes to clients;
- :func:`coerce_graph_response` — build a validated :class:`GraphResponse` from
  loose ``nodes`` / ``edges`` collections.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError

from kg_common.dto import GraphEdge, GraphNode, GraphResponse
from kg_schema.labels import ALL_LABELS
from kg_schema.relationships import EDGE_SCHEMA, SYMMETRIC_RELS, RelType

# Known node labels (метки) and relationship types (типы связей) as plain str.
KNOWN_NODE_LABELS: frozenset[str] = frozenset(str(label) for label in ALL_LABELS)
KNOWN_REL_TYPES: frozenset[str] = frozenset(str(rel) for rel in RelType)


@dataclass(frozen=True, slots=True)
class RelSignature:
    """One declarative ``(from)-[rel]->(to)`` edge signature (§3.5)."""

    from_label: str
    rel_type: str
    to_label: str

    def as_dict(self) -> dict[str, str]:
        """Serialize to the client-facing ``{from, rel, to}`` shape."""
        return {"from": self.from_label, "rel": self.rel_type, "to": self.to_label}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of :func:`validate_graph_response` (результат проверки)."""

    valid: bool
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialize to the ``{valid, errors}`` payload the API returns."""
        return {"valid": self.valid, "errors": list(self.errors)}


def coerce_graph_response(
    nodes: Iterable[GraphNode | dict[str, object]],
    edges: Iterable[GraphEdge | dict[str, object]],
) -> GraphResponse:
    """Build a validated :class:`GraphResponse` from loose nodes/edges (§3.16).

    Accepts either DTO instances or raw dicts (camelCase or snake_case keys);
    each element is run through pydantic validation.
    """
    return GraphResponse(
        nodes=[GraphNode.model_validate(n) for n in nodes],
        edges=[GraphEdge.model_validate(e) for e in edges],
    )


def validate_graph_response(payload: dict) -> dict:
    """Validate a graph payload against the schema; return ``{valid, errors}``.

    Checks (§3.16): the payload parses into a :class:`GraphResponse`; every
    ``node.type`` is a known label; every ``edge.type`` is a known relationship
    type; every ``edge.source`` / ``edge.target`` points at a node id present in
    the payload (no dangling / висячие edges).
    """
    try:
        graph = GraphResponse.model_validate(payload)
    except ValidationError as exc:
        result = ValidationResult(valid=False, errors=(f"payload does not parse: {exc}",))
        return result.as_dict()

    errors: list[str] = []
    node_ids: set[str] = set()
    for node in graph.nodes:
        node_ids.add(node.id)
        if node.type not in KNOWN_NODE_LABELS:
            errors.append(f"unknown node type {node.type!r} for node {node.id!r}")

    for edge in graph.edges:
        if edge.type not in KNOWN_REL_TYPES:
            errors.append(f"unknown relationship type {edge.type!r} for edge {edge.id!r}")
        if edge.source not in node_ids:
            errors.append(f"edge {edge.id!r} source {edge.source!r} is not a node in the payload")
        if edge.target not in node_ids:
            errors.append(f"edge {edge.id!r} target {edge.target!r} is not a node in the payload")

    return ValidationResult(valid=not errors, errors=tuple(errors)).as_dict()


def build_schema_descriptor() -> dict:
    """Return the label + relationship catalog exposed by ``/graph/schema`` (§3.16).

    Mirrors the client contract: the full label set (метки), the relationship
    type list (типы связей), and every declarative ``(from, rel, to)`` signature.
    """
    labels = sorted(KNOWN_NODE_LABELS)
    relationships = [RelSignature(str(f), str(r), str(t)).as_dict() for (f, r, t) in EDGE_SCHEMA]
    return {
        "labels": labels,
        "labelCount": len(labels),
        "relationshipTypes": sorted(KNOWN_REL_TYPES),
        "relationships": relationships,
        "relationshipCount": len(relationships),
        "symmetric": sorted(str(r) for r in SYMMETRIC_RELS),
    }
