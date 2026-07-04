"""Gaps & contradictions (§15/§24.10)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from kg_retrievers.gap_taxonomy5 import classify_gap_5way

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
    gaps = []
    for r in rows:
        code, ru = classify_gap_5way(r[2], None)
        gaps.append(
            {
                "id": r[0],
                "name": r[1],
                "type": r[2],
                "domain": r[3],
                "taxonomy5": code,
                "taxonomy5_ru": ru,
            }
        )
    return {"count": len(rows), "gaps": gaps}


@router.get("/gaps/ranked")
def gaps_ranked(limit: int = 50) -> dict:
    """Gaps ranked by priority score with RU explanation + next-experiment hint (§15.9)."""
    from kg_retrievers.gap_scoring import gap_priority_score, next_experiment_hint

    store = get_store()
    rows = store.rows(
        "MATCH (g:Node) WHERE g.label='Gap' "
        f"RETURN g.id, g.name, g.gap_type, g.domain LIMIT {int(limit)}"
    )
    gaps = []
    for r in rows:
        # absence_confidence lives in the node's JSON props, not a column
        ac = (store.get_node(r[0]) or {}).get("absence_confidence")
        g = {"id": r[0], "name": r[1], "gap_type": r[2], "domain": r[3], "absence_confidence": ac}
        g["score"] = round(gap_priority_score(g), 4)
        g["next_experiment"] = next_experiment_hint(g)
        code, ru = classify_gap_5way(g["gap_type"], g.get("absence_confidence"))
        g["taxonomy5"], g["taxonomy5_ru"] = code, ru
        gaps.append(g)
    gaps.sort(key=lambda x: x["score"], reverse=True)
    return {"count": len(gaps), "gaps": gaps}


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
