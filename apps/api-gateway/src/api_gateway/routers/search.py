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


_alias_cache: dict[str, Any] = {}


@router.get("/entities/resolve")
def entity_resolve(mention: str) -> dict:
    """Resolve a surface mention to a canonical entity id via the alias index (§3.12)."""
    from kg_retrievers.alias_index import AliasIndex

    store = get_store()
    key = store.db_path
    idx = _alias_cache.get(key)
    if idx is None:
        idx = AliasIndex.build_from_store(store)
        _alias_cache[key] = idx
    resolved = idx.resolve(mention)
    node = store.get_node(resolved) if resolved else None
    return {
        "mention": mention,
        "resolved_id": resolved,
        "name": (node or {}).get("name") if node else None,
        "matched": resolved is not None,
    }


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: str) -> dict:
    """Full entity card: props, aliases, review status, evidence + neighbour counts (§14.5)."""
    from fastapi import HTTPException

    store = get_store()
    nd = store.get_node(entity_id)
    if nd is None:
        raise HTTPException(status_code=404, detail="entity not found")
    n_ev = store.rows(
        "MATCH (:Node {id:$id})-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
        "RETURN count(e)",
        {"id": entity_id},
    )
    n_neigh = store.rows(
        "MATCH (:Node {id:$id})-[:Rel]-(m:Node) RETURN count(DISTINCT m)", {"id": entity_id}
    )
    return {
        "id": nd["id"],
        "type": nd.get("label"),
        "name": nd.get("name"),
        "canonical_name": nd.get("canonical_name"),
        "domain": nd.get("domain"),
        "aliases": (nd.get("aliases_text") or "").split("|") if nd.get("aliases_text") else [],
        "review_status": nd.get("review_status"),
        "verified": nd.get("verified"),
        "practice_type": nd.get("practice_type"),
        "evidence_count": int(n_ev[0][0]) if n_ev else 0,
        "neighbor_count": int(n_neigh[0][0]) if n_neigh else 0,
    }


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


class GlobalSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)


@router.post("/search/global")
def search_global(req: GlobalSearchRequest) -> dict:
    """GraphRAG global search over community summaries (§11.7/§11.9)."""
    from kg_retrievers.community_search import global_search

    ans = global_search(get_store(), req.query, limit=req.top_k)
    store = get_store()
    doc_ids = sorted({
        (store.get_node(e) or {}).get("doc_id")
        for e in ans.evidence_ids
        if (store.get_node(e) or {}).get("doc_id")
    })
    return {
        "query": ans.query,
        "answer": ans.answer,
        "used_community_ids": [c.community_id for c in ans.communities],
        "sources": ans.evidence_ids,
        "cited_doc_ids": doc_ids,
    }


@router.get("/graphrag/status")
def graphrag_status() -> dict:
    """Active GraphRAG index status + build version (§11.9/§11.10)."""
    store = get_store()
    rows = store.rows(
        "MATCH (f:Node) WHERE f.label='Finding' AND f.community_id IS NOT NULL RETURN count(f)"
    )
    n_summaries = int(rows[0][0]) if rows else 0
    assigned = store.rows("MATCH (n:Node) WHERE n.community_id IS NOT NULL RETURN count(n)")
    n_assigned = int(assigned[0][0]) if assigned else 0
    return {
        "build_version": f"cg-{n_summaries}",
        "communities": n_summaries,
        "nodes_assigned": n_assigned,
        "active": n_summaries > 0,
    }


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
