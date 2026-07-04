"""KG Health Score dashboard endpoint (§23.24).

Exposes ``GET /api/v1/admin/kg-health`` — the composite 0–100 health score plus a
data-quality scorecard and per-slice breakdown that names the graph's worst
areas. The scoring math lives in :mod:`kg_eval.kg_health_score` /
:mod:`kg_eval.kg_health_slice_breakdown` (already shipped); the live-graph
metric extraction lives in :mod:`api_gateway.kg_health_metrics`. This router is
a thin HTTP surface over those, running against the active graph store (Neo4j in
the server profile).

The endpoint is a read-only census, so it is cheap enough to call on demand from
the Admin UI and also serves the acceptance check: a healthy demo corpus scores
above the configurable ``min_score`` gate.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from api_gateway.kg_health_metrics import compute_kg_health

router = APIRouter(prefix="/api/v1/admin", tags=["admin", "kg-health"])

_DIMENSIONS = ("domain", "material", "property", "source_type")


@router.get("/kg-health")
def kg_health(
    dimension: str = Query(default="domain"),
    stale_years: int = Query(default=12, ge=0, le=100),
    current_year: int = Query(default=2026, ge=1900, le=2100),
    worst_k: int = Query(default=5, ge=1, le=50),
    min_score: float = Query(default=60.0, ge=0.0, le=100.0),
) -> dict:
    """Composite KG health score + data-quality scorecard + slice breakdown (§23.24).

    ``dimension`` selects the slice axis (``domain``/``material``/``property``/
    ``source_type``). ``stale_years``/``current_year`` set the source-freshness
    cutoff. ``min_score`` is the demo/CI gate the overall score must clear.
    """
    if dimension not in _DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"dimension must be one of {list(_DIMENSIONS)}",
        )
    return compute_kg_health(
        get_store(),
        dimension=dimension,
        stale_years=stale_years,
        current_year=current_year,
        worst_k=worst_k,
        min_score=min_score,
    )
