"""Agentic contradiction arbiter endpoints — где литература спорит (§15.4 / demo).

``GET /contradictions`` lists flagged contradictions with the spread of conflicting
values; ``POST /contradictions/{id}/analyze`` runs the arbiter agent
(:mod:`agent_service.contradiction_analysis`) to reason — from each side's provenance
(value, geography, vintage, evidence) — whether the conflict is genuine or explained by
differing conditions, and which side is better supported.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api_gateway.auth import current_role
from api_gateway.deps import get_store

# NB: prefix is /arbiter, not /contradictions — gaps.py already owns GET
# /api/v1/contradictions (id+name only). This router adds the agentic analysis surface.
router = APIRouter(prefix="/api/v1/arbiter", tags=["contradictions"])


@router.get("/contradictions")
def list_contradictions(limit: int = 40, _role: str = Depends(current_role)) -> dict:
    """List contradictions with the min/max spread of their conflicting values."""
    from agent_service.contradiction_analysis import list_contradictions as _list

    return {"contradictions": _list(get_store(), limit=limit)}


@router.post("/{cid:path}/analyze")
def analyze(cid: str, _role: str = Depends(current_role)) -> dict:
    """Run the arbiter agent over one contradiction and return its reasoned verdict."""
    from agent_service.contradiction_analysis import analyze_contradiction

    try:
        return analyze_contradiction(get_store(), cid).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="contradiction not found") from exc
