"""Directed centrality — HITS hubs & authorities (§3.14 / §12.8).

Complementary to the *undirected* metrics in :mod:`kg_retrievers.graph_algos`,
this module projects the ``:Entity`` subgraph of a :class:`KuzuGraphStore` into a
*directed* NetworkX graph (edge direction preserved) and runs Kleinberg's HITS
algorithm — центральность по направленным связям — yielding two scores per node:

- ``authority`` — авторитетность: high when many good *hubs* point **to** it
  (a well-cited target of ``x → z`` edges);
- ``hub`` — концентратор: high when it points **to** many good *authorities*.

Results are frozen :class:`HitsScore` dataclasses (with ``as_dict``). ``hits`` and
``top_authorities`` rank by authority (desc, ties by id); ``top_hubs`` ranks by
hub (desc, ties by id). Everything degrades gracefully on an empty graph.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

# Directed entity–entity projection (§3.14): edge direction preserved, self-loops
# dropped. Mirrors the label restriction used by the undirected projection.
_PROJECTION = (
    "MATCH (a:Node)-[:Rel]->(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id"
)


@dataclass(frozen=True)
class HitsScore:
    """An entity id paired with its HITS hub & authority scores (§12.8).

    Both scores are non-negative; across all nodes each set sums to ``1.0``
    (NetworkX normalisation), so they behave like a probability mass.
    """

    entity_id: str
    hub: float
    authority: float

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "hub": self.hub, "authority": self.authority}


def project_directed_entity_graph(store: KuzuGraphStore) -> nx.DiGraph:
    """Project the ``:Entity`` subgraph into a directed NetworkX graph (§3.14).

    Only nodes taking part in at least one entity→entity edge appear; isolated
    entities are omitted (same convention as the undirected projection).
    """
    rows = store.rows(_PROJECTION, {"l": list(ENTITY_LABELS)})
    graph = nx.DiGraph()
    graph.add_edges_from((a, b) for a, b in rows if a != b)
    return graph


def _l1_normalise(vec: dict[str, float]) -> dict[str, float]:
    """Divide a score map by its sum so the mass sums to 1.0 (§12.8)."""
    total = sum(vec.values())
    if total <= 0.0:
        return vec
    return {k: v / total for k, v in vec.items()}


def _hits_power_iteration(
    graph: nx.DiGraph, *, max_iter: int = 1000, tol: float = 1.0e-10
) -> tuple[dict[str, float], dict[str, float]]:
    """Kleinberg HITS via power iteration — no SciPy dependency (§3.14 / §12.8).

    Mirrors ``networkx.hits`` semantics (L1-normalised hub & authority maps) but
    stays pure-Python so it runs in the embedded, offline profile.
    """
    hubs = {n: 1.0 / graph.number_of_nodes() for n in graph}
    for _ in range(max_iter):
        # authority(v) = sum of hub over its predecessors (edges u -> v).
        authorities = dict.fromkeys(graph, 0.0)
        for u, v in graph.edges():
            authorities[v] += hubs[u]
        authorities = _l1_normalise(authorities)
        # hub(v) = sum of authority over its successors (edges v -> w).
        new_hubs = dict.fromkeys(graph, 0.0)
        for v, w in graph.edges():
            new_hubs[v] += authorities[w]
        new_hubs = _l1_normalise(new_hubs)
        delta = sum(abs(new_hubs[n] - hubs[n]) for n in graph)
        hubs = new_hubs
        if delta < tol:
            break
    return hubs, authorities


def _score_map(store: KuzuGraphStore) -> tuple[dict[str, float], dict[str, float]]:
    """Compute HITS hub/authority maps, or two empty maps on an empty graph."""
    graph = project_directed_entity_graph(store)
    if graph.number_of_nodes() == 0:
        return {}, {}
    return _hits_power_iteration(graph)


def hits(store: KuzuGraphStore) -> list[HitsScore]:
    """All entities scored by HITS, ranked by authority desc, ties by id (§12.8).

    An empty (or edge-less) graph yields ``[]``.
    """
    hubs, authorities = _score_map(store)
    scores = [
        HitsScore(nid, float(hubs.get(nid, 0.0)), float(authorities.get(nid, 0.0)))
        for nid in authorities
    ]
    scores.sort(key=lambda s: (-s.authority, s.entity_id))
    return scores


def top_authorities(store: KuzuGraphStore, top: int = 10) -> list[HitsScore]:
    """Top ``top`` entities by authority — авторитетность (§12.8).

    Well-cited targets rank first; ordering matches :func:`hits`.
    """
    return hits(store)[: max(top, 0)]


def top_hubs(store: KuzuGraphStore, top: int = 10) -> list[HitsScore]:
    """Top ``top`` entities by hub — концентратор (§12.8).

    Ranked by hub desc, ties broken by id. An empty graph yields ``[]``.
    """
    scores = list(hits(store))
    scores.sort(key=lambda s: (-s.hub, s.entity_id))
    return scores[: max(top, 0)]
