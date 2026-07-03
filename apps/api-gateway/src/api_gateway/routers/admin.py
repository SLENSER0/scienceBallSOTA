"""Admin / knowledge-coverage dashboard (§24.15)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/ready")
def ready() -> JSONResponse:
    """Readiness probe: 200 only if the graph store answers a query, else 503 (§14.11)."""
    checks: dict[str, str] = {}
    ok = True
    try:
        get_store().rows("MATCH (n:Node) RETURN count(n) LIMIT 1")
        checks["graph"] = "ok"
    except Exception as e:  # surface as not-ready, don't crash the probe
        checks["graph"] = f"error: {type(e).__name__}"
        ok = False
    status = 200 if ok else 503
    return JSONResponse({"ready": ok, "checks": checks}, status_code=status)

_DOMAINS = [
    "hydrometallurgy",
    "pyrometallurgy",
    "environment",
    "water_treatment",
    "waste_processing",
    "mineral_processing",
    "electrometallurgy",
]


@router.get("/stats")
def stats() -> dict:
    store = get_store()
    return {
        "counts": store.counts(),
        "by_label": store.counts_by_label(),
    }


@router.get("/lineage")
def lineage() -> dict:
    """Provenance lineage (§10): extractor/gap-scan runs and what they produced."""
    store = get_store()
    runs = store.rows(
        "MATCH (r:Node) WHERE r.label IN ['ExtractorRun','GapScanRun'] "
        "RETURN r.id, r.label, r.name, r.created_at ORDER BY r.created_at"
    )
    out = []
    for rid, label, name, created in runs:
        produced = store.rows(
            "MATCH (n:Node)-[e:Rel]->(r:Node {id:$id}) "
            "WHERE e.type IN ['EXTRACTED_BY','DETECTED_BY'] RETURN count(n)",
            {"id": rid},
        )
        by_run = store.rows(
            "MATCH (n:Node) WHERE n.extractor_run_id=$id RETURN n.label, count(n)",
            {"id": rid},
        )
        out.append(
            {
                "run_id": rid,
                "type": label,
                "name": name,
                "created_at": created,
                "produced_edges": produced[0][0] if produced else 0,
                "by_label": {r[0]: r[1] for r in by_run},
            }
        )
    return {"runs": out}


@router.post("/communities")
def communities() -> dict:
    """Detect GraphRAG communities + write summaries (§11)."""
    from kg_retrievers.community import detect_communities

    return detect_communities(get_store()).as_dict()


@router.get("/communities/global-search")
def community_global_search(q: str, limit: int = 3) -> dict:
    """GraphRAG global search: map-reduce over community summaries (§11.7/§11.9)."""
    from kg_retrievers.community_search import global_search

    return global_search(get_store(), q, limit=limit).as_dict()


@router.get("/communities/local-search")
def community_local_search(seed: str, limit: int = 15) -> dict:
    """GraphRAG local search: an entity's community members + neighbours (§11.7)."""
    from kg_retrievers.community_search import local_search

    return local_search(get_store(), seed, limit=limit)


@router.get("/validate-shapes")
def validate_shapes(limit: int = 500) -> dict:
    """SHACL-style conformance report over graph nodes — FAIR/evidence-first (§24.19)."""
    from kg_schema.shapes import validate_nodes

    store = get_store()
    rows = store.rows(f"MATCH (n:Node) RETURN n LIMIT {int(limit)}")
    nodes = [store._node_dict(r[0]) for r in rows]
    return validate_nodes(nodes)


@router.get("/absence-map")
def absence_map(domain: str | None = None) -> dict:
    """Map of the unknown: material×property absence-confidence grid (§25.11)."""
    from kg_retrievers.absence_map import build_absence_map

    return build_absence_map(get_store(), domain=domain).as_dict()


@router.get("/coverage-matrix")
def coverage_matrix() -> dict:
    """Coverage matrix + by-owner + timeline (§15.5)."""
    from kg_retrievers.coverage_matrix import (
        aggregate_gaps_by_owner,
        build_coverage_matrix,
        build_coverage_timeline,
    )

    store = get_store()
    return {
        "matrix": build_coverage_matrix(store).as_dict(),
        "by_owner": [g.as_dict() for g in aggregate_gaps_by_owner(store)],
        "timeline": [p.as_dict() for p in build_coverage_timeline(store)],
    }


@router.get("/coverage")
def coverage() -> dict:
    """Per-domain coverage metrics (§24.15): sources, facts, gaps, contradictions."""
    store = get_store()
    rows = store.rows(
        "MATCH (n:Node) WHERE n.domain IS NOT NULL RETURN n.domain, n.label, count(n)"
    )
    agg: dict[str, dict[str, int]] = {d: {} for d in _DOMAINS}
    for domain, label, cnt in rows:
        agg.setdefault(domain, {})
        agg[domain][label] = agg[domain].get(label, 0) + cnt
    out = []
    for domain, labels in agg.items():
        out.append(
            {
                "domain": domain,
                "sources": labels.get("Paper", 0) + labels.get("Document", 0),
                "technologies": labels.get("TechnologySolution", 0) + labels.get("Method", 0),
                "measurements": labels.get("Measurement", 0),
                "gaps": labels.get("Gap", 0),
                "contradictions": labels.get("Contradiction", 0),
                "risk": "high" if labels.get("Paper", 0) + labels.get("Document", 0) < 2 else "ok",
            }
        )
    return {"domains": out}
