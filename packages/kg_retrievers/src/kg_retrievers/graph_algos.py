"""GDS-lite graph algorithms over the entity graph (§12.8 GDS similarity /
centrality / paths).

A thin, offline-safe alternative to Neo4j GDS: project the ``:Entity`` subgraph
of a :class:`KuzuGraphStore` into an undirected NetworkX graph (the same
projection used by community detection, §11 / §3.14) and expose a handful of
classic graph metrics:

- ``degree_centrality`` — центральность по степени (most-connected entities);
- ``betweenness_centrality`` — центральность по посредничеству (bridge nodes);
- ``similar_entities_by_neighbourhood`` — сходство по соседству (Jaccard of the
  neighbour sets, a structural similarity);
- ``shortest_path`` — кратчайший путь between two entities.

Results are returned as frozen :class:`ScoredNode` dataclasses (with
``as_dict``) or, for paths, a plain ``list[str]`` of node ids. Everything
degrades gracefully on an empty / disconnected graph.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

# Same projection query as community detection (§11): undirected entity–entity
# edges, self-loops dropped.
_PROJECTION = (
    "MATCH (a:Node)-[:Rel]-(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id"
)


@dataclass(frozen=True)
class ScoredNode:
    """An entity id paired with a metric score (§12.8).

    ``score`` is a centrality value or a neighbourhood-similarity (Jaccard);
    both live in ``[0, 1]`` for the metrics exposed here.
    """

    entity_id: str
    score: float

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "score": self.score}


def project_entity_graph(store: KuzuGraphStore) -> nx.Graph:
    """Project the ``:Entity`` subgraph into an undirected NetworkX graph (§12.8).

    Only nodes that take part in at least one entity–entity edge appear (this
    mirrors community detection); isolated entities are intentionally omitted.
    """
    rows = store.rows(_PROJECTION, {"l": list(ENTITY_LABELS)})
    graph = nx.Graph()
    graph.add_edges_from((a, b) for a, b in rows if a != b)
    return graph


def _rank(scores: dict[str, float], top: int) -> list[ScoredNode]:
    """Rank id→score highest-first, ties broken by id for determinism (§12.8)."""
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [ScoredNode(nid, float(s)) for nid, s in ordered[: max(top, 0)]]


def degree_centrality(store: KuzuGraphStore, top: int = 10) -> list[ScoredNode]:
    """Top entities by degree centrality — центральность по степени (§12.8).

    The most-connected entity ranks first. Scores are NetworkX's normalised
    degree centrality (``degree / (n − 1)``), so they lie in ``[0, 1]``.
    """
    graph = project_entity_graph(store)
    if graph.number_of_nodes() == 0:
        return []
    return _rank(nx.degree_centrality(graph), top)


def betweenness_centrality(store: KuzuGraphStore, top: int = 10) -> list[ScoredNode]:
    """Top entities by betweenness — центральность по посредничеству (§12.8).

    Highlights bridge entities that lie on many shortest paths. Scores are
    non-negative and normalised to ``[0, 1]``.
    """
    graph = project_entity_graph(store)
    if graph.number_of_nodes() == 0:
        return []
    return _rank(nx.betweenness_centrality(graph), top)


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two neighbour sets — коэффициент Жаккара (§12.8)."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def similar_entities_by_neighbourhood(
    store: KuzuGraphStore, entity_id: str, top: int = 10
) -> list[ScoredNode]:
    """Entities structurally similar to ``entity_id`` by shared neighbours (§12.8).

    Similarity is the Jaccard index of the two entities' neighbour sets —
    сходство по соседству — in ``[0, 1]``. ``entity_id`` itself is excluded.
    An unknown / isolated ``entity_id`` yields an empty list.
    """
    graph = project_entity_graph(store)
    if entity_id not in graph:
        return []
    target = set(graph.neighbors(entity_id))
    scores: dict[str, float] = {}
    for other in graph.nodes:
        if other == entity_id:
            continue
        scores[other] = _jaccard(target, set(graph.neighbors(other)))
    return _rank(scores, top)


def shortest_path(store: KuzuGraphStore, a: str, b: str) -> list[str]:
    """Shortest path of entity ids between ``a`` and ``b`` — кратчайший путь (§12.8).

    Returns the node-id sequence (inclusive of both endpoints). A missing node
    or a disconnected pair yields ``[]``.
    """
    graph = project_entity_graph(store)
    if a not in graph or b not in graph:
        return []
    try:
        return list(nx.shortest_path(graph, a, b))
    except nx.NetworkXNoPath:
        return []
