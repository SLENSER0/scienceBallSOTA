"""Shared-neighbor co-occurrence projection (§8.12).

Projects a set of same-label nodes into a *co-occurrence* graph by counting how
many 1-hop neighbours two nodes have in common — проекция по общим соседям. Two
``Material`` nodes that both connect to the same ``Measurement`` co-occur once
through that measurement; the more shared neighbours, the stronger the pair.

This is a primitive input for a "similar materials" view that no existing module
computes: unlike a plain projection it does not collapse the graph, it *pairs*
same-label nodes and reports the shared bridge nodes (``via``).

Kuzu note: ``label`` and ``id`` are base ``Node`` columns, so the co-occurrence
pattern filters and returns them directly (custom props would need ``get_node``).
The undirected two-hop pattern ``(a)-[:Rel]-(m)-[:Rel]-(b)`` with ``a.id < b.id``
yields one row per shared neighbour ``m`` while excluding self-pairs.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

# Co-occurrence pattern (§8.12): two same-label nodes ``a``/``b`` bridged by a
# common 1-hop neighbour ``m``. ``a.id < b.id`` drops self-pairs and keeps a
# single canonical orientation per unordered pair. Only base columns are read.
_COOCCURRENCE = (
    "MATCH (a:Node)-[:Rel]-(m:Node)-[:Rel]-(b:Node) "
    "WHERE a.label = $L AND b.label = $L AND a.id < b.id "
    "RETURN a.id, b.id, m.id"
)


@dataclass(frozen=True)
class CooccurrenceEdge:
    """A pair of same-label nodes and their shared 1-hop neighbours (§8.12).

    ``a``/``b`` are the paired node ids (``a`` < ``b`` lexicographically),
    ``shared`` the count of distinct common neighbours, and ``via`` the sorted
    tuple of those neighbour ids — общие соседи, связывающие пару.
    """

    a: str
    b: str
    shared: int
    via: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "shared": self.shared, "via": tuple(sorted(self.via))}


def shared_neighbor_cooccurrence(store: KuzuGraphStore, label: str) -> list[CooccurrenceEdge]:
    """Project same-``label`` nodes into shared-neighbour co-occurrence edges (§8.12).

    Every unordered pair of ``label`` nodes that shares at least one 1-hop
    neighbour becomes one :class:`CooccurrenceEdge`; a pair with no common
    neighbour produces no edge, and self-pairs are impossible (``a.id < b.id``).
    Results are ranked by ``shared`` descending, ties broken by ``(a, b)``.
    An empty store returns ``[]``.
    """
    pairs: dict[tuple[str, str], set[str]] = {}
    for a, b, m in store.rows(_COOCCURRENCE, {"L": label}):
        if a == b:  # defensive: never a self-pair
            continue
        pairs.setdefault((a, b), set()).add(m)
    edges = [
        CooccurrenceEdge(a=a, b=b, shared=len(via), via=tuple(sorted(via)))
        for (a, b), via in pairs.items()
    ]
    edges.sort(key=lambda e: (-e.shared, e.a, e.b))
    return edges
