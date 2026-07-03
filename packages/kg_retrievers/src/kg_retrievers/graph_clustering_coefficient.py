"""Local clustering-coefficient & triangle analytics over the entity graph (§8.13).

Коэффициент кластеризации / clustering coefficient — measures local cohesion: how
tightly a node's neighbours are interconnected. We project every ``Rel`` edge onto
an **undirected** simple graph (direction dropped, self-loops and parallel edges
collapsed), then compute per-node figures with pure python.

Definitions (undirected simple graph):
- ``local_clustering[v]`` = ``2 * e_v / (k_v * (k_v - 1))`` where ``k_v`` is the
  degree of ``v`` and ``e_v`` the number of edges among its neighbours; ``0.0``
  when ``k_v < 2`` (no possible triangle). Диапазон / range ``[0, 1]``.
- ``triangle_counts[v]`` = ``e_v`` — number of triangles through ``v``; the total
  triangle count is ``sum(triangle_counts) / 3``.
- ``transitivity`` = ``3 * triangles / triples`` = ``sum(e_v) / sum(C(k_v, 2))``,
  the global fraction of connected triples that are closed; ``0.0`` when there are
  no connected triples.
- ``average_clustering`` = the mean of ``local_clustering`` over all nodes; ``0.0``
  on an empty store.

This module reads a :class:`KuzuGraphStore` (never writes). It pulls every edge via
``MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id`` and every node id via
``MATCH (n:Node) RETURN n.id``.

Kuzu note: custom node props are not queryable columns, so we RETURN only the base
``id`` columns here; anything else would be read via ``store.get_node``.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

_ALL_NODES = "MATCH (n:Node) RETURN n.id"
_ALL_EDGES = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id"


@dataclass(frozen=True)
class ClusteringResult:
    """Clustering-coefficient summary of the undirected entity projection (§8.13).

    ``local`` — коэффициент кластеризации по узлам / per-node clustering coefficient;
    ``triangles`` — число треугольников через узел / triangles through each node;
    ``transitivity`` — глобальная транзитивность / global transitivity;
    ``average_clustering`` — средний локальный коэффициент / mean local coefficient.
    """

    local: dict[str, float]
    triangles: dict[str, int]
    transitivity: float
    average_clustering: float

    def as_dict(self) -> dict:
        return {
            "local": dict(self.local),
            "triangles": {k: int(v) for k, v in self.triangles.items()},
            "transitivity": self.transitivity,
            "average_clustering": self.average_clustering,
        }


def _adjacency(store: KuzuGraphStore) -> dict[str, set[str]]:
    """Build the undirected simple-graph adjacency (self-loops/parallels dropped)."""
    adj: dict[str, set[str]] = {}
    for (nid,) in store.rows(_ALL_NODES):
        adj.setdefault(nid, set())
    for src, dst in store.rows(_ALL_EDGES):
        adj.setdefault(src, set())
        adj.setdefault(dst, set())
        if src == dst:
            continue  # ignore self-loops
        adj[src].add(dst)
        adj[dst].add(src)
    return adj


def _neighbour_edges(node: str, neighbours: set[str], adj: dict[str, set[str]]) -> int:
    """Count edges among ``node``'s neighbours (each undirected edge once)."""
    nbrs = sorted(neighbours)
    count = 0
    for i, a in enumerate(nbrs):
        a_adj = adj[a]
        for b in nbrs[i + 1 :]:
            if b in a_adj:
                count += 1
    return count


def local_clustering(store: KuzuGraphStore) -> dict[str, float]:
    """Per-node local clustering coefficient over the undirected projection (§8.13)."""
    adj = _adjacency(store)
    result: dict[str, float] = {}
    for node, neighbours in adj.items():
        k = len(neighbours)
        if k < 2:
            result[node] = 0.0
            continue
        e = _neighbour_edges(node, neighbours, adj)
        result[node] = 2.0 * e / (k * (k - 1))
    return result


def triangle_counts(store: KuzuGraphStore) -> dict[str, int]:
    """Number of triangles passing through each node (§8.13)."""
    adj = _adjacency(store)
    return {node: _neighbour_edges(node, neighbours, adj) for node, neighbours in adj.items()}


def clustering_report(store: KuzuGraphStore) -> ClusteringResult:
    """Full clustering summary: local, triangles, transitivity, average (§8.13)."""
    adj = _adjacency(store)
    local: dict[str, float] = {}
    triangles: dict[str, int] = {}
    closed = 0  # sum of e_v == 3 * (#triangles)
    triples = 0  # sum of C(k_v, 2) == connected triples
    for node, neighbours in adj.items():
        k = len(neighbours)
        e = _neighbour_edges(node, neighbours, adj)
        triangles[node] = e
        closed += e
        triples += k * (k - 1) // 2
        local[node] = 0.0 if k < 2 else 2.0 * e / (k * (k - 1))

    transitivity = closed / triples if triples else 0.0
    average_clustering = sum(local.values()) / len(local) if local else 0.0
    return ClusteringResult(
        local=local,
        triangles=triangles,
        transitivity=transitivity,
        average_clustering=average_clustering,
    )
