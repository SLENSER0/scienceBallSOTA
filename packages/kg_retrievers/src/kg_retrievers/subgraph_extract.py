"""Ego- and induced-subgraph extraction over :class:`KuzuGraphStore` (§8.12).

Two bounded, offline-safe views over the entity graph, both returning a plain
``{"nodes": [...], "edges": [...]}`` payload of hand-checkable dicts:

- :func:`ego_subgraph` — эго-подграф: a bounded breadth-first expansion around a
  ``center_id`` out to ``radius`` hops, capped at ``max_nodes`` nodes;
- :func:`induced_subgraph` — индуцированный подграф: the subgraph induced by an
  explicit set of node ids.

Both reuse the store's traversal primitives without re-querying edges by hand:
:meth:`KuzuGraphStore.neighbors` for one-hop expansion and
:meth:`KuzuGraphStore.edges_among` for the induced edge set — so the invariant
"edges only among included nodes" holds by construction. Node payloads come from
:meth:`KuzuGraphStore.get_node`, which reads the JSON ``props`` catch-all as well
as the base columns (custom props are not queryable Kuzu columns, §3 / ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import GraphEdge
from kg_retrievers.graph_store import KuzuGraphStore


@dataclass(frozen=True)
class Subgraph:
    """A bounded graph view: node dicts plus the edges induced among them (§8.12)."""

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Serialise to the ``{"nodes", "edges"}`` payload (copies each dict)."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
        }


def _edge_dict(edge: GraphEdge) -> dict[str, Any]:
    """Flatten a :class:`GraphEdge` DTO to a compact directed-edge dict (§8.12)."""
    return {"id": edge.id, "source": edge.source, "target": edge.target, "type": edge.type}


def _induced_edges(store: KuzuGraphStore, ids: set[str]) -> tuple[dict[str, Any], ...]:
    """Edges of the store whose both endpoints lie in ``ids``, ordered for stability."""
    edges = [_edge_dict(e) for e in store.edges_among(ids)]
    edges.sort(key=lambda e: (e["source"], e["type"], e["target"]))
    return tuple(edges)


def _one_hop_ids(store: KuzuGraphStore, node_id: str) -> list[str]:
    """Sorted ids of ``node_id``'s direct neighbours — соседи (reuses ``neighbors``).

    Traversal is undirected (the store expands ``-[:Rel*1..1]-``); the sort makes
    the ``max_nodes`` cap deterministic and therefore hand-checkable.
    """
    resp = store.neighbors(node_id, depth=1)
    return sorted(n.id for n in resp.nodes if n.id != node_id)


def ego_subgraph(
    store: KuzuGraphStore,
    center_id: str,
    *,
    radius: int = 1,
    max_nodes: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    """Эго-подграф: bounded BFS around ``center_id`` (§8.12).

    Expands breadth-first out to ``radius`` hops, adding nodes in sorted order and
    stopping once ``max_nodes`` nodes (the centre included) have been collected. The
    result's edges are exactly those induced among the collected nodes. An unknown
    ``center_id`` (or ``max_nodes < 1``) yields an empty ``{"nodes": [], "edges": []}``.
    """
    center = store.get_node(center_id)
    if center is None or max_nodes < 1:
        return Subgraph((), ()).as_dict()

    visited: set[str] = {center_id}
    order: list[str] = [center_id]
    frontier: list[str] = [center_id]
    capped = False
    for _ in range(max(0, radius)):
        if capped or not frontier:
            break
        next_frontier: list[str] = []
        for node_id in frontier:
            for neighbour in _one_hop_ids(store, node_id):
                if neighbour in visited:
                    continue
                if len(visited) >= max_nodes:
                    capped = True
                    break
                visited.add(neighbour)
                order.append(neighbour)
                next_frontier.append(neighbour)
            if capped:
                break
        frontier = next_frontier

    nodes = tuple(nd for nid in order if (nd := store.get_node(nid)) is not None)
    return Subgraph(nodes, _induced_edges(store, visited)).as_dict()


def induced_subgraph(
    store: KuzuGraphStore,
    node_ids: list[str] | set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Индуцированный подграф over an explicit id set (§8.12).

    Keeps only the ids that resolve to real nodes and returns the edges induced
    among them. Unknown ids are dropped silently; an empty / all-unknown input
    yields ``{"nodes": [], "edges": []}``.
    """
    present: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for nid in sorted(set(node_ids)):
        nd = store.get_node(nid)
        if nd is not None:
            present.add(nid)
            nodes.append(nd)
    return Subgraph(tuple(nodes), _induced_edges(store, present)).as_dict()
