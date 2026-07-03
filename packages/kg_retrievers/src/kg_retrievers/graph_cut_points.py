"""Graph hygiene — articulation points & bridges over the entity graph (§8.16).

Точки сочленения и мосты / articulation points and bridges — the single points of
failure in KG connectivity. In the undirected entity projection an *articulation
point* is a node whose removal increases the number of connected components; a
*bridge* is an edge whose removal does the same. They flag structural weaknesses:
a bridge is the only path between two otherwise separate regions of the graph.

This module reads a :class:`KuzuGraphStore` (never writes). It pulls every edge
via ``MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id`` and every node id via
``MATCH (n:Node) RETURN n.id``, builds an undirected adjacency, then runs an
iterative DFS (Hopcroft–Tarjan low-link) over each component. Self-loops and
parallel edges are collapsed so a doubled edge is never mistaken for a bridge.

Kuzu note: custom node props are not queryable columns, so we RETURN only the
base ``id`` columns here; anything else would be read via ``store.get_node``.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

_ALL_NODES = "MATCH (n:Node) RETURN n.id"
_ALL_EDGES = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id"


@dataclass(frozen=True)
class ConnectivityReport:
    """Single points of failure in the entity graph (§8.16).

    ``articulation_points`` — отсортированные id узлов-сочленений / sorted cut-node
    ids; ``bridges`` — отсортированный список мостов, каждый — отсортированная пара
    концов / sorted list of bridge edges, each a sorted endpoint pair.
    """

    articulation_points: tuple[str, ...]
    bridges: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict:
        return {
            "articulation_points": self.articulation_points,
            "bridges": [list(b) for b in self.bridges],
        }


def _adjacency(store: KuzuGraphStore) -> dict[str, set[str]]:
    """Build undirected adjacency; isolated nodes get empty neighbour sets."""
    adj: dict[str, set[str]] = {}
    for (nid,) in store.rows(_ALL_NODES):
        adj.setdefault(nid, set())
    for src, dst in store.rows(_ALL_EDGES):
        adj.setdefault(src, set())
        adj.setdefault(dst, set())
        if src == dst:
            continue  # self-loops cannot be bridges or create cut points
        adj[src].add(dst)
        adj[dst].add(src)
    return adj


def _articulation_and_bridges(
    adj: dict[str, set[str]],
) -> tuple[set[str], list[tuple[str, str]]]:
    """Iterative Hopcroft–Tarjan low-link scan over every component.

    Returns the set of articulation-point ids and the list of bridge edges (each
    endpoint pair sorted). Order of discovery is not relied upon; callers sort.
    """
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    counter = 0
    arts: set[str] = set()
    bridges: list[tuple[str, str]] = []

    for start in adj:
        if start in disc:
            continue
        parent[start] = None
        # stack of (node, iterator over its neighbours)
        stack: list[tuple[str, object]] = [(start, iter(sorted(adj[start])))]
        disc[start] = low[start] = counter
        counter += 1
        root_children = 0
        while stack:
            node, it = stack[-1]
            advanced = False
            for nbr in it:  # type: ignore[assignment]
                if nbr == parent[node]:
                    continue
                if nbr in disc:
                    low[node] = min(low[node], disc[nbr])
                else:
                    parent[nbr] = node
                    disc[nbr] = low[nbr] = counter
                    counter += 1
                    if node == start:
                        root_children += 1
                    stack.append((nbr, iter(sorted(adj[nbr]))))
                    advanced = True
                    break
            if advanced:
                continue
            # done with `node` — pop and fold its low-link into its parent
            stack.pop()
            par = parent[node]
            if par is not None:
                low[par] = min(low[par], low[node])
                if low[node] > disc[par]:
                    bridges.append(tuple(sorted((par, node))))  # type: ignore[arg-type]
                if par != start and low[node] >= disc[par]:
                    arts.add(par)
        if root_children > 1:
            arts.add(start)
    return arts, bridges


def articulation_points(store: KuzuGraphStore) -> set[str]:
    """Node ids whose removal disconnects the undirected projection (§8.16)."""
    arts, _ = _articulation_and_bridges(_adjacency(store))
    return arts


def bridges(store: KuzuGraphStore) -> list[tuple[str, str]]:
    """Bridge edges (each endpoint pair sorted), sorted for determinism (§8.16)."""
    _, brs = _articulation_and_bridges(_adjacency(store))
    return sorted(brs)


def connectivity_report(store: KuzuGraphStore) -> ConnectivityReport:
    """Full report of articulation points and bridges over ``store`` (§8.16)."""
    arts, brs = _articulation_and_bridges(_adjacency(store))
    return ConnectivityReport(
        articulation_points=tuple(sorted(arts)),
        bridges=tuple(sorted(brs)),
    )
