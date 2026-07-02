"""Gaps & contradictions (§15/§24.10)."""

from __future__ import annotations

from fastapi import APIRouter

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["gaps"])


@router.get("/gaps")
def list_gaps(limit: int = 100) -> dict:
    rows = get_store().rows(
        "MATCH (g:Node) WHERE g.label='Gap' RETURN g.id, g.name, g.gap_type, g.domain "
        f"LIMIT {int(limit)}"
    )
    return {
        "count": len(rows),
        "gaps": [{"id": r[0], "name": r[1], "type": r[2], "domain": r[3]} for r in rows],
    }


@router.get("/contradictions")
def list_contradictions(limit: int = 100) -> dict:
    rows = get_store().rows(
        f"MATCH (c:Node) WHERE c.label='Contradiction' RETURN c.id, c.name LIMIT {int(limit)}"
    )
    return {"count": len(rows), "contradictions": [{"id": r[0], "name": r[1]} for r in rows]}


@router.post("/gaps/scan")
def scan() -> dict:
    from kg_retrievers.gap_analysis import GapScanner

    return GapScanner(get_store()).scan().as_dict()
