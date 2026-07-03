"""Graph endpoints (§3.16 / §6.2): schema, neighbors, subgraph."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_gateway.deps import get_store
from kg_common import GraphResponse
from kg_schema import EDGE_SCHEMA, NodeLabel, RelType
from kg_schema.enums import GapType, MetallurgicalDomain, PracticeGeography

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])
entities_router = APIRouter(prefix="/api/v1/entities", tags=["entities"])


@router.get("/schema")
def schema() -> dict:
    return {
        "version": "0.1.0",
        "labels": [str(x) for x in NodeLabel],
        "relationships": [{"from": f, "rel": r, "to": t} for f, r, t in EDGE_SCHEMA],
        "rel_types": [str(x) for x in RelType],
        "enums": {
            "GapType": [str(x) for x in GapType],
            "MetallurgicalDomain": [str(x) for x in MetallurgicalDomain],
            "PracticeGeography": [str(x) for x in PracticeGeography],
        },
    }


class SubgraphRequest(BaseModel):
    node_ids: list[str]
    expand: int = 1


@router.post("/subgraph", response_model=GraphResponse)
def subgraph(req: SubgraphRequest) -> GraphResponse:
    return get_store().subgraph_from_ids(req.node_ids, expand=req.expand)


@entities_router.get("/{entity_id}/neighbors", response_model=GraphResponse)
def neighbors(entity_id: str, depth: int = Query(default=1, ge=1, le=4)) -> GraphResponse:
    return get_store().neighbors(entity_id, depth=depth)


@router.get("/nodes")
def nodes(
    label: str | None = None,
    domain: str | None = None,
    limit: int = Query(default=50, le=500),
) -> dict:
    """Filtered node listing — a safe, parameterized graph query (no raw Cypher, §14.6)."""
    store = get_store()
    where = ["n.name IS NOT NULL"]
    params: dict = {}
    if label:
        where.append("n.label = $label")
        params["label"] = label
    if domain:
        where.append("n.domain = $domain")
        params["domain"] = domain
    cypher = f"MATCH (n:Node) WHERE {' AND '.join(where)} RETURN n LIMIT {int(limit)}"
    rows = store.rows(cypher, params)
    items = [store._node_dict(r[0]) for r in rows]
    return {
        "count": len(items),
        "nodes": [
            {
                "id": n["id"],
                "type": n.get("label"),
                "name": n.get("name"),
                "domain": n.get("domain"),
            }
            for n in items
        ],
    }


@router.get("/path")
def path(source: str, target: str, max_hops: int = Query(default=4, ge=1, le=6)) -> dict:
    """Shortest path (BFS) between two entities (§14.6)."""
    store = get_store()
    if store.get_node(source) is None or store.get_node(target) is None:
        return {"found": False, "path": [], "hops": None}
    from collections import deque

    prev: dict[str, str | None] = {source: None}
    frontier: deque[tuple[str, int]] = deque([(source, 0)])
    while frontier:
        nid, dist = frontier.popleft()
        if nid == target:
            chain = [nid]
            while prev[chain[-1]] is not None:
                chain.append(prev[chain[-1]])  # type: ignore[arg-type]
            chain.reverse()
            return {"found": True, "hops": dist, "path": chain}
        if dist >= max_hops:
            continue
        for r in store.rows(
            "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) RETURN DISTINCT m.id", {"id": nid}
        ):
            if r[0] not in prev:
                prev[r[0]] = nid
                frontier.append((r[0], dist + 1))
    return {"found": False, "path": [], "hops": None}
