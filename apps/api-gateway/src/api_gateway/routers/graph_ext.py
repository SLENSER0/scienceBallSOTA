"""Graph traversal endpoints — query / expand (§14.6 / §6.2 / §5.3).

Дополнительные graph-эндпоинты сверх :mod:`api_gateway.routers.graph`
(schema / subgraph / neighbors / path). Реализуют «тяжёлые» обходы графа с
серверными лимитами ``max_nodes`` / ``max_edges`` (§14.6): при превышении
результат усекается и возвращается флаг ``truncated=true`` вместо падения.

This is a SEPARATE ``APIRouter`` object (tag ``graph-ext``) sharing the
``/api/v1/graph`` prefix with :mod:`api_gateway.routers.graph` — the two routers
expose different paths (``/query``, ``/expand``) so they never collide.

Kuzu note (§14.6): custom node/edge props are NOT queryable columns, so the
read-templates ``RETURN`` base columns (ids) only and every node's full property
bag is read back via :meth:`KuzuGraphStore.get_node`. Payloads follow the §5.3
``GraphResponse`` shape (camelCase ``evidenceCount`` / ``missingFields`` /
``evidenceIds``) with an extra top-level ``truncated`` flag.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/graph", tags=["graph-ext"])

# Server-side caps for the expand endpoint (which has no per-request caps, §14.6).
_MAX_NODES = 200
_MAX_EDGES = 400
_MAX_DEPTH = 2  # one/two-hop expansion only (§5.2.3 expand)

# Edge read-template: base columns only, filtered to the resolved node set.
_EDGES_CYPHER = (
    "MATCH (a:Node)-[r:Rel]->(b:Node) WHERE a.id IN $ids AND b.id IN $ids "
    "{rel} RETURN a.id, r.type, b.id, r.confidence, r.evidence_ids, "
    "r.contradicted, r.inferred LIMIT {cap}"
)


# -- payload dataclasses (§5.3 GraphResponse shape) ----------------------------
@dataclass(frozen=True)
class GraphNodePayload:
    """Один узел graph-ответа / one GraphResponse node (§5.3)."""

    id: str
    label: str  # display label (name / canonical_name / id)
    type: str  # ontology label (Material, Experiment, Gap, …)
    confidence: float | None
    evidence_count: int | None
    verified: bool | None
    missing_fields: list[str] | None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "confidence": self.confidence,
            "evidenceCount": self.evidence_count,
            "verified": self.verified,
            "missingFields": self.missing_fields,
        }


@dataclass(frozen=True)
class GraphEdgePayload:
    """Одно ребро graph-ответа / one GraphResponse edge (§5.3)."""

    id: str
    source: str
    target: str
    type: str
    confidence: float | None
    inferred: bool | None
    contradicted: bool | None
    evidence_ids: list[str] | None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "confidence": self.confidence,
            "inferred": self.inferred,
            "contradicted": self.contradicted,
            "evidenceIds": self.evidence_ids,
        }


# -- request models ------------------------------------------------------------
class GraphQueryRequest(BaseModel):
    """Filtered graph query body (§6.2). All filters optional; caps always apply."""

    node_ids: list[str] | None = None
    labels: list[str] | None = None
    rel_types: list[str] | None = None
    max_nodes: int = Field(default=200, ge=0, le=2000)
    max_edges: int = Field(default=400, ge=0, le=5000)
    timeout_ms: int | None = Field(default=None, ge=0)


class GraphExpandRequest(BaseModel):
    """Seed-based neighbourhood expansion body (§6.2 / §5.2.3)."""

    node_ids: list[str]
    depth: int = Field(default=1, ge=1, le=_MAX_DEPTH)
    types: list[str] | None = None


# -- helpers -------------------------------------------------------------------
def _norm_evidence_ids(value: Any) -> list[str] | None:
    """Normalise an edge ``evidence_ids`` cell (list from fake, JSON str from Kuzu)."""
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return [str(x) for x in parsed] if isinstance(parsed, list) else None
    return None


def _node_payload(nd: dict[str, Any]) -> GraphNodePayload:
    """Build a §5.3 node payload from a full ``get_node`` property bag."""
    return GraphNodePayload(
        id=nd["id"],
        label=nd.get("name") or nd.get("canonical_name") or nd["id"],
        type=nd.get("label") or "Entity",
        confidence=nd.get("confidence"),
        evidence_count=nd.get("evidence_count"),
        verified=nd.get("verified"),
        missing_fields=nd.get("missing_fields"),
    )


def _edge_payload(row: list[Any]) -> GraphEdgePayload:
    """Build a §5.3 edge payload from an ``_EDGES_CYPHER`` row."""
    src, rtype, dst, conf, eids, contra, inferred = row
    return GraphEdgePayload(
        id=f"{src}|{rtype}|{dst}",
        source=src,
        target=dst,
        type=rtype,
        confidence=conf,
        inferred=inferred,
        contradicted=contra,
        evidence_ids=_norm_evidence_ids(eids),
    )


def _select_node_ids(
    store: Any, node_ids: list[str] | None, labels: list[str] | None, cap: int
) -> list[str]:
    """Pick candidate node ids by id/label filter (base column ``n.id`` only)."""
    where: list[str] = []
    params: dict[str, Any] = {}
    if node_ids is not None:
        where.append("n.id IN $node_ids")
        params["node_ids"] = node_ids
    if labels:
        where.append("n.label IN $labels")
        params["labels"] = labels
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    cypher = f"MATCH (n:Node){clause} RETURN n.id LIMIT {cap + 1}"
    return [r[0] for r in store.rows(cypher, params)]


def _collect_nodes(
    store: Any, ids: list[str], cap: int
) -> tuple[list[GraphNodePayload], list[str], bool]:
    """Resolve ids → node payloads via ``get_node``; cap to ``max_nodes`` (§14.6)."""
    truncated = len(ids) > cap
    kept_ids = ids[:cap]
    nodes: list[GraphNodePayload] = []
    resolved: list[str] = []
    for nid in kept_ids:
        nd = store.get_node(nid)
        if nd:
            nodes.append(_node_payload(nd))
            resolved.append(nid)
    return nodes, resolved, truncated


def _collect_edges(
    store: Any, ids: list[str], rel_types: list[str] | None, cap: int
) -> tuple[list[GraphEdgePayload], bool]:
    """Edges among ``ids`` (optionally by rel type); cap to ``max_edges`` (§14.6)."""
    if not ids:
        return [], False
    rel = "AND r.type IN $rel_types" if rel_types else ""
    cypher = _EDGES_CYPHER.format(rel=rel, cap=cap + 1)
    params: dict[str, Any] = {"ids": ids}
    if rel_types:
        params["rel_types"] = rel_types
    rows = store.rows(cypher, params)
    truncated = len(rows) > cap
    edges = [_edge_payload(r) for r in rows[:cap]]
    return edges, truncated


def _expand_ids(
    store: Any, seeds: list[str], depth: int, types: list[str] | None, cap: int
) -> list[str]:
    """One/two-hop neighbour ids from ``seeds`` (reuse the neighbors pattern, §14.6)."""
    rel = "AND b.label IN $types " if types else ""
    cypher = (
        f"MATCH (a:Node)-[:Rel*1..{depth}]-(b:Node) WHERE a.id IN $ids "
        f"{rel}RETURN DISTINCT b.id LIMIT {cap}"
    )
    params: dict[str, Any] = {"ids": seeds}
    if types:
        params["types"] = types
    return [r[0] for r in store.rows(cypher, params)]


# -- endpoints -----------------------------------------------------------------
@router.post("/query")
def graph_query(req: GraphQueryRequest) -> dict:
    """Filtered graph query → §5.3 payload with a heavy-query ``truncated`` guard (§14.6)."""
    store = get_store()
    ids = _select_node_ids(store, req.node_ids, req.labels, req.max_nodes)
    nodes, kept, node_trunc = _collect_nodes(store, ids, req.max_nodes)
    edges, edge_trunc = _collect_edges(store, kept, req.rel_types, req.max_edges)
    return {
        "nodes": [n.as_dict() for n in nodes],
        "edges": [e.as_dict() for e in edges],
        "truncated": node_trunc or edge_trunc,
    }


@router.post("/expand")
def graph_expand(req: GraphExpandRequest) -> dict:
    """One/two-hop expansion around seed nodes → §5.3 payload (§14.6 / §5.2.3)."""
    store = get_store()
    if not req.node_ids:
        return {"nodes": [], "edges": [], "truncated": False}
    depth = max(1, min(req.depth, _MAX_DEPTH))
    neighbours = _expand_ids(store, req.node_ids, depth, req.types, _MAX_NODES)
    # Seeds first, then neighbours; order-preserving dedup (§5.2.3 keeps the seed).
    all_ids = list(dict.fromkeys([*req.node_ids, *neighbours]))
    nodes, kept, node_trunc = _collect_nodes(store, all_ids, _MAX_NODES)
    edges, edge_trunc = _collect_edges(store, kept, None, _MAX_EDGES)
    return {
        "nodes": [n.as_dict() for n in nodes],
        "edges": [e.as_dict() for e in edges],
        "truncated": node_trunc or edge_trunc,
    }
