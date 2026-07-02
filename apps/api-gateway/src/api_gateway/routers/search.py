"""Entity search + glossary (§3.12 / §24.3)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/entities/search")
def entity_search(
    q: str = Query(min_length=1),
    type: str | None = None,
    limit: int = Query(default=20, le=100),
) -> dict:
    store = get_store()
    term = q.lower()
    cypher = (
        "MATCH (n:Node) WHERE (lower(n.name) CONTAINS $t OR lower(n.aliases_text) CONTAINS $t "
        "OR lower(n.canonical_name) CONTAINS $t)"
    )
    params: dict = {"t": term}
    if type:
        cypher += " AND n.label = $label"
        params["label"] = type
    cypher += f" RETURN n LIMIT {int(limit)}"
    rows = store.rows(cypher, params)
    results = []
    for r in rows:
        nd = store._node_dict(r[0])
        results.append(
            {
                "id": nd["id"],
                "type": nd.get("label"),
                "name": nd.get("name"),
                "domain": nd.get("domain"),
                "practice_type": nd.get("practice_type"),
                "aliases": nd.get("aliases_text"),
            }
        )
    return {"query": q, "count": len(results), "results": results}


@router.get("/domain/glossary")
def glossary(q: str | None = None, lang: str | None = None, type: str | None = None) -> dict:
    from kg_schema.taxonomy import load_taxonomy

    idx = load_taxonomy()
    out = []
    for e in idx.entries:
        if type and e.node_type != type:
            continue
        if q and q.lower() not in " ".join(e.all_terms).lower():
            continue
        out.append(
            {
                "id": e.id,
                "type": e.node_type,
                "canonical_ru": e.canonical_ru,
                "canonical_en": e.canonical_en,
                "aliases": list(e.aliases),
                "domain": e.domain,
                "source": e.source_file,
            }
        )
    return {"count": len(out), "terms": out}
