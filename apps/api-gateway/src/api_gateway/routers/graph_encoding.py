"""Fully visual-encoded live graph payloads (§3.16 / §5.2.3).

The base ``/api/v1/graph`` traversal endpoints return payloads whose derived
visual-encoding fields (``missingFields``, ``evidenceCount``, ``contradicted``
for CONTRADICTS edges) are left empty. This router serves the SAME live-Neo4j
(server profile) traversal, then runs :func:`enrich_visual_encoding` so every
§5.2.3 code is populated before the payload reaches the «клубок»:

* полый узел = нет данных (``missingFields``),
* красное ребро = противоречие (``contradicted``),
* пунктир = inferred, замок = verified (carried verbatim by the store DTO),
* размер/толщина = evidence count, прозрачность = confidence.

Endpoints
---------
* ``GET  /api/v1/graph/encoding/legend`` — machine-readable legend of the codes.
* ``GET  /api/v1/graph/encoding/neighbors/{entity_id}`` — encoded neighbourhood.
* ``POST /api/v1/graph/encoding/subgraph`` — encoded subgraph from seed ids.
* ``GET  /api/v1/graph/encoding/sample`` — encoded neighbourhood of the highest-
  degree node, so the legend view has live data with no user input.

All traversal + payload building is delegated to the shared store; this router
only wires HTTP → store → pure enrichment (no raw Cypher from clients).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api_gateway.deps import get_store
from api_gateway.graph_visual_encoding import (
    VISUAL_ENCODING_LEGEND,
    enrich_visual_encoding,
)
from kg_common import GraphResponse

router = APIRouter(prefix="/api/v1/graph/encoding", tags=["graph"])


def _encoding_summary(resp: GraphResponse) -> dict[str, int]:
    """Roll up how many nodes/edges carry each visual code (for the UI header)."""
    return {
        "nodes": len(resp.nodes),
        "edges": len(resp.edges),
        "hollow": sum(1 for n in resp.nodes if n.missing_fields),
        "verified": sum(1 for n in resp.nodes if n.verified),
        "contradicted": sum(1 for e in resp.edges if e.contradicted),
        "inferred": sum(1 for e in resp.edges if e.inferred),
    }


class EncodedGraph(BaseModel):
    """Fully §5.2.3-encoded payload plus a per-code count summary."""

    graph: GraphResponse
    summary: dict[str, int]
    seed: str | None = None


class SubgraphRequest(BaseModel):
    node_ids: list[str]
    expand: int = 1


@router.get("/legend")
def legend() -> dict[str, Any]:
    """The visual-encoding legend so the «клубок» is readable without docs (§5.2.3)."""
    return {"encodings": VISUAL_ENCODING_LEGEND}


@router.get("/neighbors/{entity_id}", response_model=EncodedGraph)
def neighbors(entity_id: str, depth: int = Query(default=1, ge=1, le=4)) -> EncodedGraph:
    store = get_store()
    if store.get_node(entity_id) is None:
        raise HTTPException(status_code=404, detail=f"entity {entity_id!r} not found")
    resp = enrich_visual_encoding(store.neighbors(entity_id, depth=depth))
    return EncodedGraph(graph=resp, summary=_encoding_summary(resp), seed=entity_id)


@router.post("/subgraph", response_model=EncodedGraph)
def subgraph(req: SubgraphRequest) -> EncodedGraph:
    store = get_store()
    resp = enrich_visual_encoding(store.subgraph_from_ids(req.node_ids, expand=req.expand))
    return EncodedGraph(graph=resp, summary=_encoding_summary(resp))


@router.get("/sample", response_model=EncodedGraph)
def sample(depth: int = Query(default=2, ge=1, le=3)) -> EncodedGraph:
    """Encoded neighbourhood of the busiest node — instant demo data (§5.2.3)."""
    store = get_store()
    rows = store.rows(
        "MATCH (n:Node)-[r:Rel]-() RETURN n.id, count(r) AS d ORDER BY d DESC LIMIT 1"
    )
    if not rows or not rows[0] or rows[0][0] is None:
        empty = GraphResponse()
        return EncodedGraph(graph=empty, summary=_encoding_summary(empty), seed=None)
    seed = rows[0][0]
    resp = enrich_visual_encoding(store.neighbors(seed, depth=depth))
    return EncodedGraph(graph=resp, summary=_encoding_summary(resp), seed=seed)
