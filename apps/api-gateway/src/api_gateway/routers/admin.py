"""Admin / knowledge-coverage dashboard (§24.15)."""

from __future__ import annotations

from fastapi import APIRouter

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

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


@router.post("/communities")
def communities() -> dict:
    """Detect GraphRAG communities + write summaries (§11)."""
    from kg_retrievers.community import detect_communities

    return detect_communities(get_store()).as_dict()


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
