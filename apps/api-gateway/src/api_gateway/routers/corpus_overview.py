"""Corpus-overview endpoint for the WebGL large-graph mode (§17.9, §5.1, §10 Mode C).

The Reagraph/2D canvas caps a rendered subgraph at a few hundred nodes for
readability. The Sigma.js + Graphology *large-graph* mode instead paints the
**whole corpus** (tens of thousands of nodes) at once, coloured by community, as
a fast WebGL overview. That needs a payload the per-node ``GraphResponse``
builders cannot cheaply produce — ``subgraph_from_ids`` reads every node with an
individual query, which is fine for 600 nodes but not for 66k.

This router adds ``GET /api/v1/graph/corpus/overview`` — a *lightweight, bulk*
projection of the graph built from exactly two aggregate reads (edges, then node
metadata for the touched ids). It never allocates a DTO per node; each node/edge
is a flat dict with only the fields Sigma reducers need (id, name, type,
communityId, degree). Communities are read from the ``community_id`` that
``detect_communities`` (§11) persists, and — when the corpus has never been
clustered — computed lazily once via that same routine, so the colouring here
and the community-summaries panel share one source of truth. Per-community
sizes, representative entities and (when present) the GraphRAG ``Finding`` text
summary are returned alongside so the client community panel is self-contained.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/graph/corpus", tags=["graph-corpus"])

# Community-summary artifact label written by detect_communities (§11); excluded
# from the entity projection but mined for per-community text summaries.
_FINDING = "Finding"


def _has_communities(store) -> bool:  # type: ignore[no-untyped-def]
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id IS NOT NULL RETURN n.id LIMIT 1"
    )
    return bool(rows)


def _summaries(store) -> dict[int, str]:  # type: ignore[no-untyped-def]
    """Map community_id → GraphRAG text summary (empty when none persisted)."""
    rows = store.rows(
        "MATCH (f:Node) WHERE f.label=$f AND f.community_id IS NOT NULL "
        "RETURN f.community_id, coalesce(f.text, f.name, '')",
        {"f": _FINDING},
    )
    out: dict[int, str] = {}
    for cid_raw, text in rows:
        try:
            out[int(cid_raw)] = str(text or "")
        except (TypeError, ValueError):
            continue
    return out


@router.get("/overview")
def overview(
    edge_limit: int = Query(default=8000, ge=100, le=200_000),
    min_degree: int = Query(default=0, ge=0, le=50),
    cluster: bool = Query(default=True),
    max_communities: int = Query(default=60, ge=1, le=500),
) -> dict:
    """Bulk, WebGL-ready projection of the whole corpus graph (§17.9).

    ``edge_limit`` bounds the render budget (edges drive which nodes appear).
    ``min_degree`` prunes leaf nodes for a cleaner overview. When ``cluster`` is
    set and the corpus was never clustered, Louvain community detection runs once
    (persisting ``community_id``) so every node can be coloured by community.
    """
    store = get_store()

    # Ensure community colouring exists (lazy, one-off, shared with the panel).
    if cluster and not _has_communities(store):
        from kg_retrievers.community import detect_communities

        detect_communities(store, min_size=2)

    # 1) Edges first — they define the visible node set and the render budget.
    edge_rows = store.rows(
        "MATCH (a:Node)-[r:Rel]->(b:Node) "
        "RETURN a.id, b.id, r.type, coalesce(r.contradicted,false), coalesce(r.inferred,false) "
        f"LIMIT {int(edge_limit)}",
    )

    degree: dict[str, int] = {}
    raw_edges: list[dict] = []
    for a, b, rtype, contra, inferred in edge_rows:
        if not a or not b or a == b:
            continue
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
        raw_edges.append(
            {
                "source": a,
                "target": b,
                "type": rtype or "REL",
                "contradicted": bool(contra),
                "inferred": bool(inferred),
            }
        )

    total = store.counts()
    total_edges = total.get("rels", 0)
    truncated = len(raw_edges) < total_edges and len(edge_rows) >= int(edge_limit)

    keep = {nid for nid, d in degree.items() if d >= max(1, min_degree)}
    if not keep:
        return {
            "nodes": [],
            "edges": [],
            "communities": [],
            "stats": {
                "nodeCount": 0,
                "edgeCount": 0,
                "communityCount": 0,
                "totalNodes": total.get("nodes", 0),
                "totalEdges": total_edges,
                "truncated": truncated,
            },
        }

    # 2) Node metadata for exactly the touched ids (single bulk read).
    meta_rows = store.rows(
        "MATCH (n:Node) WHERE n.id IN $ids AND n.label <> $f "
        "RETURN n.id, coalesce(n.name, n.id), coalesce(n.label,'Entity'), "
        "n.community_id, coalesce(n.domain,'')",
        {"ids": list(keep), "f": _FINDING},
    )

    nodes: list[dict] = []
    comm_size: dict[int, int] = {}
    comm_names: dict[int, list[str]] = {}
    comm_domains: dict[int, set[str]] = {}
    valid_ids: set[str] = set()
    for nid, name, label, cid_raw, domain in meta_rows:
        cid: int | None
        try:
            cid = int(cid_raw) if cid_raw is not None else None
        except (TypeError, ValueError):
            cid = None
        valid_ids.add(nid)
        nodes.append(
            {
                "id": nid,
                "name": name or nid,
                "type": label or "Entity",
                "communityId": cid,
                "degree": degree.get(nid, 0),
                "domain": domain or None,
            }
        )
        if cid is not None:
            comm_size[cid] = comm_size.get(cid, 0) + 1
            comm_domains.setdefault(cid, set())
            if domain:
                comm_domains[cid].add(domain)
            names = comm_names.setdefault(cid, [])
            if name and len(names) < 8:
                names.append(name)

    # Drop edges whose endpoints were filtered out (e.g. Finding nodes / min_degree).
    edges = [e for e in raw_edges if e["source"] in valid_ids and e["target"] in valid_ids]

    summaries = _summaries(store)
    communities = [
        {
            "id": cid,
            "size": size,
            "topEntities": comm_names.get(cid, []),
            "domains": sorted(comm_domains.get(cid, set())),
            "summary": summaries.get(cid, ""),
        }
        for cid, size in comm_size.items()
    ]
    communities.sort(key=lambda c: c["size"], reverse=True)
    communities = communities[:max_communities]

    return {
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "stats": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "communityCount": len(comm_size),
            "totalNodes": total.get("nodes", 0),
            "totalEdges": total_edges,
            "truncated": truncated,
        },
    }
