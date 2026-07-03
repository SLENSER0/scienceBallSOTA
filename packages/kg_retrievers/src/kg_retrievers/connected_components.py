"""Weakly-connected component analytics over the entity graph (§8.13).

Компоненты слабой связности / weakly-connected components — the graph partitioned
into maximal sets of nodes reachable from one another when every ``Rel`` edge is
treated as undirected. Isolated nodes (no edges at all) form their own singleton
components.

This module reads a :class:`KuzuGraphStore` (never writes). It pulls every edge
via ``MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id`` and every node id via
``MATCH (n:Node) RETURN n.id``, then runs a pure-python union-find (disjoint set)
over those ids so that even edge-less nodes are represented.

Kuzu note: custom node props are not queryable columns, so we RETURN only the
base ``id`` columns here; anything else would be read via ``store.get_node``.
Partitioning the id sets is reliable on empty and disconnected graphs alike.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

_ALL_NODES = "MATCH (n:Node) RETURN n.id"
_ALL_EDGES = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id"


class _UnionFind:
    """Disjoint-set forest with path compression and union by size."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._size: dict[str, int] = {}

    def add(self, item: str) -> None:
        if item not in self._parent:
            self._parent[item] = item
            self._size[item] = 1

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        # path compression
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._size[ra] < self._size[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]

    def groups(self) -> list[list[str]]:
        clusters: dict[str, list[str]] = {}
        for item in self._parent:
            clusters.setdefault(self.find(item), []).append(item)
        return list(clusters.values())


@dataclass(frozen=True)
class Component:
    """One weakly-connected component (§8.13).

    ``members`` — отсортированные id узлов / sorted node ids; ``size`` — их число.
    """

    members: tuple[str, ...]
    size: int

    def as_dict(self) -> dict:
        return {"members": list(self.members), "size": self.size}


@dataclass(frozen=True)
class ComponentReport:
    """Summary of the graph's weakly-connected components (§8.13).

    ``n_components`` — число компонент / component count; ``components`` —
    отсортированы по убыванию размера / sorted by size descending;
    ``largest_fraction`` — доля узлов в крупнейшей компоненте / share of nodes in
    the largest one; ``singletons`` — число одиночных узлов / isolated-node count.
    """

    n_components: int
    components: tuple[Component, ...]
    largest_fraction: float
    singletons: int

    def as_dict(self) -> dict:
        return {
            "n_components": self.n_components,
            "components": [c.as_dict() for c in self.components],
            "largest_fraction": self.largest_fraction,
            "singletons": self.singletons,
        }


def connected_components(store: KuzuGraphStore) -> ComponentReport:
    """Partition ``store`` into weakly-connected components (§8.13).

    Every ``Rel`` edge is treated as undirected; isolated nodes become singletons.
    Components are sorted by size descending, ties broken by smallest member id.
    """
    uf = _UnionFind()
    for (nid,) in store.rows(_ALL_NODES):
        uf.add(nid)
    for src, dst in store.rows(_ALL_EDGES):
        # nodes always exist, but guard against dangling endpoints just in case
        uf.add(src)
        uf.add(dst)
        uf.union(src, dst)

    total_nodes = len(uf._parent)
    components = tuple(
        Component(members=tuple(sorted(group)), size=len(group)) for group in uf.groups()
    )
    components = tuple(sorted(components, key=lambda c: (-c.size, c.members[0])))

    largest_size = components[0].size if components else 0
    largest_fraction = largest_size / total_nodes if total_nodes else 0.0
    singletons = sum(1 for c in components if c.size == 1)
    return ComponentReport(
        n_components=len(components),
        components=components,
        largest_fraction=largest_fraction,
        singletons=singletons,
    )
