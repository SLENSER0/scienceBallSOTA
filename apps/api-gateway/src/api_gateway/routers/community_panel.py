"""Community-summaries panel endpoints (§17.9 / §11 GraphRAG Mode C, SOTA #3).

Surfaces the GraphRAG *community summaries* that ``detect_communities`` already
writes (one ``Finding`` summary node per cluster, tagged with ``community_id``)
so the graph UI can show a text overview of the corpus structure *next to* the
cluster colouring and let the user focus/filter a single community's subgraph.

Read-only and cheap: it reads the already-persisted ``Finding`` summaries and
member entities directly from the graph store. Community detection is expensive
and mutating, so it is only triggered lazily — when the corpus has never been
clustered — by delegating to :func:`kg_retrievers.community.detect_communities`
(the same routine ``/api/v1/admin/communities`` runs). The per-community
subgraph reuses :meth:`store.subgraph_from_ids`, the exact builder the graph
canvas already consumes (``GraphResponse`` with ``communityId`` on every node).
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from api_gateway.deps import get_store
from kg_common import GraphResponse

router = APIRouter(prefix="/api/v1/graph-communities", tags=["graph-communities"])

# The community-summary artifact label written by detect_communities (§11).
_FINDING = "Finding"


def _read_summaries(store) -> list[list]:  # type: ignore[no-untyped-def]
    """Read persisted ``(community_id, name, text)`` community-summary Findings."""
    return store.rows(
        "MATCH (f:Node) WHERE f.label=$f AND f.community_id IS NOT NULL "
        "RETURN f.community_id, coalesce(f.name,''), coalesce(f.text,'')",
        {"f": _FINDING},
    )


def _members(store, cid: int) -> list[list]:  # type: ignore[no-untyped-def]
    """Member entities of a community (its Finding artifact excluded)."""
    return store.rows(
        "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>$f "
        "RETURN n.id, coalesce(n.name,''), coalesce(n.domain,''), n.label",
        {"c": cid, "f": _FINDING},
    )


def _members_by_community(store) -> dict[int, list[list]]:  # type: ignore[no-untyped-def]
    """All clustered members grouped by ``community_id`` in ONE graph scan (§17.9).

    Заменяет N+1 (по одному полному скану ``n.community_id=$c`` на каждую общину — а у
    Kuzu/Neo4j нет вторичного индекса по ``community_id``) единственным сканом всех
    кластеризованных узлов. Каждый член отдаётся в том же виде ``[id, name, domain,
    label]``, что и :func:`_members`, поэтому вызывающая логика не меняется.
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id IS NOT NULL AND n.label<>$f "
        "RETURN n.community_id, n.id, coalesce(n.name,''), coalesce(n.domain,''), n.label",
        {"f": _FINDING},
    )
    grouped: dict[int, list[list]] = {}
    for cid_raw, nid, name, domain, label in rows:
        grouped.setdefault(int(cid_raw), []).append([nid, name, domain, label])
    return grouped


@router.get("/summaries")
def summaries(
    limit: int = Query(default=30, ge=1, le=200),
    min_size: int = Query(default=2, ge=1, le=50),
) -> dict:
    """List GraphRAG community summaries for the panel (§17.9).

    Returns one entry per detected community — its text summary, size, domains,
    representative entities and member ids (for click-to-focus). Communities are
    detected lazily only if the corpus has never been clustered.
    """
    store = get_store()
    rows = _read_summaries(store)
    if not rows:
        # Never clustered yet — run detection once (writes the Finding summaries),
        # then re-read so the panel and click-to-focus share the same source.
        from kg_retrievers.community import detect_communities

        detect_communities(store, min_size=min_size)
        rows = _read_summaries(store)

    # One batched scan of all clustered members (was: one full scan per community).
    members_by_cid = _members_by_community(store)

    communities: list[dict] = []
    for cid_raw, name, text in rows:
        cid = int(cid_raw)
        members = members_by_cid.get(cid, [])
        if len(members) < min_size:
            continue
        domains = sorted({str(d) for _, _, d, _ in members if d})
        top_entities = [nm for _, nm, _, _ in members if nm][:8]
        communities.append(
            {
                "community_id": cid,
                "title": name or f"Кластер знаний #{cid}",
                "summary": text,
                "size": len(members),
                "domains": domains,
                "top_entities": top_entities,
                "member_ids": [mid for mid, *_ in members],
            }
        )

    communities.sort(key=lambda c: c["size"], reverse=True)
    return {"count": len(communities), "communities": communities[:limit]}


@router.get("/{community_id}/subgraph", response_model=GraphResponse)
def community_subgraph(
    community_id: int,
    expand: int = Query(default=0, ge=0, le=2),
) -> GraphResponse:
    """Subgraph of one community's members (§17.9 click → focus/filter).

    ``expand`` optionally pulls in N hops of neighbours so the cluster is shown in
    context. Nodes carry ``communityId`` so the canvas can keep the cluster
    colouring. An unknown/empty community yields an empty payload.
    """
    store = get_store()
    member_ids = [str(r[0]) for r in _members(store, community_id)]
    if not member_ids:
        return GraphResponse(nodes=[], edges=[])
    return store.subgraph_from_ids(member_ids, expand=expand)
