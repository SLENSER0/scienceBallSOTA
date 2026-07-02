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
