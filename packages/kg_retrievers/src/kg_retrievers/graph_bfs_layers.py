"""Bounded BFS layers over :class:`KuzuGraphStore`'s entity graph (§8.12).

Pure-python traversal — обход в ширину без networkx. Unlike
:func:`subgraph_extract.ego_subgraph`, which returns an ego *blob* of nodes and
induced edges, this module reports the traversal *structure*: per-node hop
distance from the seed and the layered ordering of nodes by distance.

The undirected entity edges are pulled **once** via :meth:`KuzuGraphStore.rows`
(base columns only — custom props are not queryable Kuzu columns, §3 / ADR-0005)
into an in-memory adjacency dict; a bounded BFS then walks it out to ``max_depth``
hops. Neighbour iteration is sorted so distances and layers are deterministic and
hand-checkable.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

_EDGE_CYPHER = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id"


@dataclass(frozen=True)
class BfsLayers:
    """Result of a bounded BFS from ``seed`` — расстояния и слои (§8.12).

    - ``distances`` — hop distance of every reached node (seed maps to ``0``);
    - ``layers`` — nodes grouped by distance, ``layers[k]`` holding the sorted
      nodes at exactly ``k`` hops (so ``layers[0] == (seed,)`` when seed exists);
    - ``reached`` — the set of all reached node ids (always includes ``seed``
      when the seed node exists in the store).
    """

    seed: str
    distances: dict[str, int]
    layers: tuple[tuple[str, ...], ...]
    reached: frozenset[str]

    def as_dict(self) -> dict[str, object]:
        """Serialise to a plain JSON-friendly payload (§8.12).

        ``distances`` is a plain ``dict[str, int]`` and ``layers`` is a list of
        sorted lists, so the result is stable and hand-checkable.
        """
        return {
            "seed": self.seed,
            "distances": {node: int(dist) for node, dist in self.distances.items()},
            "layers": [sorted(layer) for layer in self.layers],
            "reached": sorted(self.reached),
        }


def _adjacency(store: KuzuGraphStore) -> dict[str, set[str]]:
    """Build an undirected adjacency dict from one edge pull — список смежности."""
    adj: dict[str, set[str]] = {}
    for src, dst in store.rows(_EDGE_CYPHER):
        adj.setdefault(src, set()).add(dst)
        adj.setdefault(dst, set()).add(src)
    return adj


def bfs_layers(store: KuzuGraphStore, seed: str, max_depth: int = 3) -> BfsLayers:
    """Bounded BFS from ``seed`` returning distances and layered ordering (§8.12).

    An unknown ``seed`` (no such node) yields empty ``distances`` / ``layers`` and
    an empty ``reached``. Otherwise the seed is at distance ``0`` and the walk
    expands one hop per level up to ``max_depth`` hops (``max_depth <= 0`` keeps
    only the seed layer).
    """
    if store.get_node(seed) is None:
        return BfsLayers(seed, {}, (), frozenset())

    adj = _adjacency(store)
    distances: dict[str, int] = {seed: 0}
    layers: list[tuple[str, ...]] = [(seed,)]
    frontier: list[str] = [seed]
    depth = 0
    while frontier and depth < max(0, max_depth):
        depth += 1
        next_layer: list[str] = []
        for node in frontier:
            for neighbour in sorted(adj.get(node, ())):
                if neighbour not in distances:
                    distances[neighbour] = depth
                    next_layer.append(neighbour)
        if next_layer:
            layers.append(tuple(sorted(next_layer)))
        frontier = sorted(next_layer)

    return BfsLayers(seed, distances, tuple(layers), frozenset(distances))
