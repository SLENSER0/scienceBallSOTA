"""GraphRAG community detection + summaries (§11 / §10.1 Mode C, §3.14 GDS-lite).

Builds a NetworkX projection of the entity graph, detects communities
(greedy modularity), writes ``community_id`` back onto nodes, and produces a
short template summary per community (top entities + their domains). An OSS LLM
can enrich the summary; the template keeps it offline-safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_common import get_logger, make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

_log = get_logger("community")


@dataclass
class CommunityResult:
    communities: int = 0
    nodes_assigned: int = 0
    summaries: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "communities": self.communities,
            "nodes_assigned": self.nodes_assigned,
            "summaries": self.summaries,
        }


def detect_communities(store: KuzuGraphStore, *, min_size: int = 2) -> CommunityResult:
    import networkx as nx

    labels = list(ENTITY_LABELS)
    rows = store.rows(
        "MATCH (a:Node)-[:Rel]-(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id",
        {"l": labels},
    )
    graph = nx.Graph()
    graph.add_edges_from((a, b) for a, b in rows if a != b)
    if graph.number_of_nodes() == 0:
        return CommunityResult()

    comms = sorted(nx.community.greedy_modularity_communities(graph), key=len, reverse=True)
    res = CommunityResult()
    with store.batch():
        for cid, members in enumerate(comms):
            if len(members) < min_size:
                continue
            for nid in members:
                store.execute(
                    "MATCH (n:Node {id:$id}) SET n.community_id=$c", {"id": nid, "c": cid}
                )
            res.nodes_assigned += len(members)
            res.communities += 1
            res.summaries.append(_summarize(store, cid, list(members)))
    _log.info("community.detect", **{k: v for k, v in res.as_dict().items() if k != "summaries"})
    return res


def _summarize(store: KuzuGraphStore, cid: int, member_ids: list[str]) -> dict:
    names: list[str] = []
    domains: set[str] = set()
    for nid in member_ids[:25]:
        nd = store.get_node(nid)
        if nd:
            names.append(nd.get("name") or nid)
            if nd.get("domain"):
                domains.add(nd["domain"])
    title = ", ".join(names[:5])
    summary_id = make_id("Finding", f"community-{cid}")
    text = (
        f"Кластер знаний #{cid} ({len(member_ids)} сущностей): {title}. "
        f"Домены: {', '.join(sorted(domains)) or '—'}."
    )
    store.upsert_node(
        summary_id,
        "Finding",
        name=f"Community summary #{cid}",
        text=text,
        community_id=cid,
        review_status="pending",
    )
    return {
        "community_id": cid,
        "size": len(member_ids),
        "domains": sorted(domains),
        "top_entities": names[:8],
        "summary": text,
    }
