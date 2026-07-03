"""Gaps & contradictions (§15/§24.10)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["gaps"])


@router.get("/gaps")
def list_gaps(gap_type: str | None = None, domain: str | None = None, limit: int = 100) -> dict:
    where = ["g.label='Gap'"]
    params: dict = {}
    if gap_type:
        where.append("g.gap_type = $gt")
        params["gt"] = gap_type
    if domain:
        where.append("g.domain = $dom")
        params["dom"] = domain
    rows = get_store().rows(
        f"MATCH (g:Node) WHERE {' AND '.join(where)} "
        f"RETURN g.id, g.name, g.gap_type, g.domain LIMIT {int(limit)}",
        params,
    )
    return {
        "count": len(rows),
        "gaps": [{"id": r[0], "name": r[1], "type": r[2], "domain": r[3]} for r in rows],
    }


@router.get("/gaps/matrix")
def gaps_matrix(limit: int = 200) -> dict:
    """Gap counts per (type × domain) — a coverage matrix view (§15.5/§15.7)."""
    rows = get_store().rows(
        "MATCH (g:Node) WHERE g.label='Gap' "
        f"RETURN coalesce(g.gap_type,'?'), coalesce(g.domain,'?'), count(*) LIMIT {int(limit)}"
    )
    matrix: dict[str, dict[str, int]] = {}
    for gtype, dom, cnt in rows:
        matrix.setdefault(gtype, {})[dom] = int(cnt)
    return {"matrix": matrix}


@router.get("/gaps/{gap_id}")
def gap_detail(gap_id: str) -> dict:
    store = get_store()
    nd = store.get_node(gap_id)
    if nd is None or nd.get("label") != "Gap":
        raise HTTPException(status_code=404, detail="gap not found")
    about = store.rows(
        "MATCH (g:Node {id:$g})-[:Rel {type:'ABOUT'}]->(m:Node) RETURN m.id, m.name", {"g": gap_id}
    )
    return {
        "id": nd["id"],
        "name": nd.get("name"),
        "type": nd.get("gap_type"),
        "domain": nd.get("domain"),
        "absence_confidence": nd.get("absence_confidence"),
        "review_status": nd.get("review_status"),
        "about": [{"id": a[0], "name": a[1]} for a in about],
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
