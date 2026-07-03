"""k-core decomposition over the entity graph (§8.13 analytics).

k-ядерная декомпозиция / k-core decomposition — the ``k``-core of a graph is the
maximal subgraph in which every node has degree at least ``k`` within that
subgraph. A node's *core number* is the largest ``k`` for which it belongs to the
``k``-core. Peripheral nodes (pendants, isolates) get low core numbers; densely
interconnected hubs get high ones, so core numbers expose the layered "onion"
structure of the graph.

This module reads a :class:`KuzuGraphStore` (never writes). It projects the
``:Entity`` subgraph into an undirected NetworkX graph — the same projection used
by community detection (§11) and GDS-lite (§12.8) — with self-loops dropped, as
``networkx.core_number`` requires a graph without self-loops. Both endpoints of
every entity–entity edge appear, so a node reachable by any edge is scored.

Kuzu note: custom node props are not queryable columns, so the projection RETURNs
only the base ``id`` columns and filters on ``label``; anything else would be read
via ``store.get_node``.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

# Same projection as community detection (§11) / GDS-lite (§12.8): undirected
# entity–entity edges, self-loops dropped downstream.
_PROJECTION = (
    "MATCH (a:Node)-[:Rel]-(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id"
)


@dataclass(frozen=True)
class KCoreResult:
    """k-core decomposition of the entity graph (§8.13).

    ``core_numbers`` — id → core number / номер ядра каждого узла;
    ``max_core`` — наибольший номер ядра / the highest core number present
    (``0`` on an empty graph); ``max_core_members`` — отсортированные id узлов
    максимального ядра / sorted ids of the nodes achieving ``max_core``.
    """

    core_numbers: dict[str, int]
    max_core: int
    max_core_members: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "core_numbers": dict(self.core_numbers),
            "max_core": self.max_core,
            "max_core_members": list(self.max_core_members),
        }


def _project(store: KuzuGraphStore) -> nx.Graph:
    """Project the ``:Entity`` subgraph into an undirected graph (§8.13).

    Self-loops are dropped, as ``networkx.core_number`` requires a graph without
    them. Nodes appear only if they take part in at least one entity–entity edge.
    """
    rows = store.rows(_PROJECTION, {"l": list(ENTITY_LABELS)})
    graph = nx.Graph()
    graph.add_edges_from((a, b) for a, b in rows if a != b)
    return graph


def core_numbers(store: KuzuGraphStore) -> dict[str, int]:
    """Core number of every entity node — номер ядра каждого узла (§8.13).

    Returns a plain ``{id: core_number}`` dict; empty when the graph has no
    entity–entity edges.
    """
    graph = _project(store)
    if graph.number_of_nodes() == 0:
        return {}
    return dict(nx.core_number(graph))


def kcore_report(store: KuzuGraphStore) -> KCoreResult:
    """Summarise the k-core decomposition of ``store`` (§8.13).

    ``max_core`` is the largest core number present (``0`` on an empty graph);
    ``max_core_members`` are its members, sorted by id for determinism.
    """
    numbers = core_numbers(store)
    if not numbers:
        return KCoreResult(core_numbers={}, max_core=0, max_core_members=())
    max_core = max(numbers.values())
    members = tuple(sorted(nid for nid, k in numbers.items() if k == max_core))
    return KCoreResult(core_numbers=numbers, max_core=max_core, max_core_members=members)


def k_core_members(store: KuzuGraphStore, k: int) -> set[str]:
    """Ids belonging to the ``k``-core — узлы с номером ядра ≥ ``k`` (§8.13).

    A node is in the ``k``-core iff its core number is at least ``k``. Returns an
    empty set when no node reaches ``k`` (including any ``k`` on an empty graph).
    """
    return {nid for nid, core in core_numbers(store).items() if core >= k}
