"""Entity search + glossary (§3.12 / §24.3)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def _entity_rows(store, term: str, limit: int) -> list[dict]:  # type: ignore[no-untyped-def]
    rows = store.rows(
        "MATCH (n:Node) WHERE n.name IS NOT NULL AND ("
        "lower(n.name) CONTAINS $t OR lower(coalesce(n.aliases_text,'')) CONTAINS $t "
        "OR lower(coalesce(n.canonical_name,'')) CONTAINS $t "
        "OR lower(coalesce(n.text,'')) CONTAINS $t) "
        f"RETURN n LIMIT {int(limit) * 4}",
        {"t": term.lower()},
    )
    return [store._node_dict(r[0]) for r in rows]


def _keyword_score(node: dict, tokens: set[str]) -> float:
    hay = _TOKEN.findall(
        " ".join(
            str(node.get(k) or "") for k in ("name", "aliases_text", "canonical_name", "text")
        ).lower()
    )
    hayset = set(hay)
    return len(tokens & hayset) / (len(tokens) or 1)


def _fmt(node: dict, score: float | None = None) -> dict:
    out = {
        "id": node["id"],
        "type": node.get("label"),
        "name": node.get("name"),
        "domain": node.get("domain"),
        "aliases": node.get("aliases_text"),
    }
    if score is not None:
        out["score"] = round(score, 4)
    return out


class SearchFilters(BaseModel):
    min_confidence: float | None = None
    verified_only: bool = False
    material: str | None = None
    property: str | None = None
    domain: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)  # invalid → 422
    filters: SearchFilters = Field(default_factory=SearchFilters)
    weights: dict[str, float] | None = None


def _passes_filters(node: dict, f: SearchFilters) -> bool:
    if f.verified_only and node.get("verified") is not True:
        return False
    if f.min_confidence is not None:
        conf = node.get("confidence")
        if not isinstance(conf, (int, float)) or conf < f.min_confidence:
            return False
    if f.domain and node.get("domain") != f.domain:
        return False
    return not (f.material and f.material.lower() not in str(node.get("name", "")).lower())


def _hit(node: dict, score: float) -> dict[str, Any]:
    """Unified hit shape across all three search modes (§14.7)."""
    return {
        "id": node["id"],
        "text": node.get("text") or node.get("name"),
        "score": round(score, 4),
        "doc_id": node.get("doc_id"),
        "page": node.get("page"),
        "type": node.get("label"),
        "name": node.get("name"),
        "metadata": {"domain": node.get("domain"), "review_status": node.get("review_status")},
    }


def _run_search(req: SearchRequest, mode: str) -> dict:
    from kg_retrievers.scoring import evidence_quality_score, weighted_fuse

    store = get_store()
    tokens = {t.lower() for t in _TOKEN.findall(req.query)}
    nodes = {
        n["id"]: n
        for n in _entity_rows(store, req.query, req.top_k)
        if _passes_filters(n, req.filters)
    }
    kw = {i: _keyword_score(n, tokens) for i, n in nodes.items()}
    if mode == "keyword":
        ranked = sorted(kw.items(), key=lambda x: x[1], reverse=True)[: req.top_k]
        hits = [_hit(nodes[i], s) for i, s in ranked]
    else:  # hybrid / vector both fuse keyword + evidence_quality in the embedded profile
        comps = {
            "keyword": kw,
            "evidence_quality": {i: evidence_quality_score(n) for i, n in nodes.items()},
        }
        fused = weighted_fuse(comps, req.weights or {"keyword": 0.7, "evidence_quality": 0.3})
        hits = [_hit(nodes[f.id], f.score) for f in fused[: req.top_k]]
    return {"query": req.query, "mode": mode, "count": len(hits), "hits": hits}


@router.post("/search/hybrid")
def post_search_hybrid(req: SearchRequest) -> dict:
    return _run_search(req, "hybrid")


@router.post("/search/vector")
def post_search_vector(req: SearchRequest) -> dict:
    return _run_search(req, "vector")


@router.post("/search/keyword")
def post_search_keyword(req: SearchRequest) -> dict:
    return _run_search(req, "keyword")


@router.get("/search/keyword")
def search_keyword(q: str = Query(min_length=1), limit: int = Query(default=10, le=100)) -> dict:
    store = get_store()
    tokens = {t.lower() for t in _TOKEN.findall(q)}
    scored = sorted(
        ((_keyword_score(n, tokens), n) for n in _entity_rows(store, q, limit)),
        key=lambda x: x[0],
        reverse=True,
    )
    return {
        "query": q,
        "mode": "keyword",
        "count": len(scored[:limit]),
        "results": [_fmt(n, s) for s, n in scored[:limit]],
    }


@router.get("/search/hybrid")
def search_hybrid(q: str = Query(min_length=1), limit: int = Query(default=10, le=100)) -> dict:
    from kg_retrievers.scoring import evidence_quality_score, weighted_fuse

    store = get_store()
    tokens = {t.lower() for t in _TOKEN.findall(q)}
    nodes = {n["id"]: n for n in _entity_rows(store, q, limit)}
    comps = {
        "keyword": {i: _keyword_score(n, tokens) for i, n in nodes.items()},
        "evidence_quality": {i: evidence_quality_score(n) for i, n in nodes.items()},
    }
    fused = weighted_fuse(comps, {"keyword": 0.7, "evidence_quality": 0.3})
    top = fused[:limit]
    return {
        "query": q,
        "mode": "hybrid",
        "count": len(top),
        "results": [_fmt(nodes[f.id], f.score) for f in top],
    }


@router.get("/search/vector")
def search_vector(q: str = Query(min_length=1), limit: int = Query(default=10, le=100)) -> dict:
    # Dense entity search when an index exists; otherwise degrade to keyword.
    store = get_store()
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        idx = EntityVectorIndex()
        if idx.count() > 0:
            hits = idx.similar_entities(q, k=limit)
            return {
                "query": q,
                "mode": "vector",
                "degraded": False,
                "count": len(hits),
                "results": [_fmt(store.get_node(h.id) or {"id": h.id}, h.score) for h in hits],
            }
    except Exception:
        pass
    kw = search_keyword(q, limit)
    kw["mode"] = "vector"
    kw["degraded"] = True
    return kw


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
