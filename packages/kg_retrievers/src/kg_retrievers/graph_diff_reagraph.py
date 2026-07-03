"""Reagraph-formatted graph diff — status-tagged node/edge lists (§16.10).

Take an existing :class:`~kg_retrievers.graph_diff.GraphDiff` (added / removed / changed)
and re-shape it into the single flat node/edge lists that the Reagraph UI renders, where
*every* element carries a ``status`` tag (``added`` / ``removed`` / ``changed``) so the
front-end can colour the delta (§16.10 acceptance: «рендерится в Reagraph-совместимом
формате с пометками статуса»).

Каждый узел (node) diff'а превращается в один словарь ``{id, status, data}``:

- ``added`` — data несёт снимок свойств нового узла;
- ``removed`` — data несёт снимок свойств удалённого узла;
- ``changed`` — data['changes'] несёт карту поле → ``[before, after]`` (до/после).

Каждое добавленное/удалённое ребро (edge) — один словарь ``{id, status, data}``. Рёбра
диффятся только по ключу, поэтому статуса ``changed`` для рёбер нет.

Pure Python: consumes an already-computed ``GraphDiff`` (or its :meth:`GraphDiff.as_dict`
mapping) and writes nothing back — no store, no LLM, no clock, deterministic per input.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_diff import GraphDiff

# Status tags emitted per element (§16.10). Edges only ever use added/removed.
STATUS_ADDED = "added"
STATUS_REMOVED = "removed"
STATUS_CHANGED = "changed"


@dataclass(frozen=True)
class ReagraphDiff:
    """Reagraph-ready diff: flat status-tagged node/edge lists + counts (§16.10).

    ``nodes`` / ``edges`` are tuples of ``{id, status, data}`` dicts. ``counts`` maps
    ``added_nodes`` / ``removed_nodes`` / ``changed_nodes`` / ``added_edges`` /
    ``removed_edges`` → their totals.
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    counts: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable view; ``counts`` is materialised as a plain ``dict``."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "counts": dict(self.counts),
        }


def _as_graph_diff(diff: GraphDiff | Mapping[str, Any]) -> GraphDiff:
    """Coerce a ``GraphDiff`` or its mapping form into a ``GraphDiff`` (§16.10).

    A mapping is read via the same keys :meth:`GraphDiff.as_dict` emits; missing keys
    read as empty so a partial hand-made mapping still formats cleanly.
    """
    if isinstance(diff, GraphDiff):
        return diff
    return GraphDiff(
        added_nodes=dict(diff.get("added_nodes", {})),
        removed_nodes=dict(diff.get("removed_nodes", {})),
        changed_nodes=dict(diff.get("changed_nodes", {})),
        added_edges=dict(diff.get("added_edges", {})),
        removed_edges=dict(diff.get("removed_edges", {})),
    )


def to_reagraph(diff: GraphDiff | Mapping[str, Any]) -> ReagraphDiff:
    """Format a graph diff into a :class:`ReagraphDiff` (§16.10).

    Emits one node dict per added / removed / changed node and one edge dict per added /
    removed edge, each tagged with its ``status``. Node ids are unique in the output
    because a node belongs to exactly one bucket (added ∪ removed ∪ changed). Ordering
    is deterministic: nodes then edges, each bucket in sorted-key order.
    """
    gd = _as_graph_diff(diff)

    nodes: list[dict[str, Any]] = []
    for nid in sorted(gd.added_nodes):
        nodes.append({"id": nid, "status": STATUS_ADDED, "data": dict(gd.added_nodes[nid])})
    for nid in sorted(gd.removed_nodes):
        nodes.append({"id": nid, "status": STATUS_REMOVED, "data": dict(gd.removed_nodes[nid])})
    for nid in sorted(gd.changed_nodes):
        changes = {f: list(delta) for f, delta in gd.changed_nodes[nid].items()}
        nodes.append({"id": nid, "status": STATUS_CHANGED, "data": {"changes": changes}})

    edges: list[dict[str, Any]] = []
    for key in sorted(gd.added_edges):
        edges.append({"id": key, "status": STATUS_ADDED, "data": dict(gd.added_edges[key])})
    for key in sorted(gd.removed_edges):
        edges.append({"id": key, "status": STATUS_REMOVED, "data": dict(gd.removed_edges[key])})

    counts: dict[str, int] = {
        "added_nodes": len(gd.added_nodes),
        "removed_nodes": len(gd.removed_nodes),
        "changed_nodes": len(gd.changed_nodes),
        "added_edges": len(gd.added_edges),
        "removed_edges": len(gd.removed_edges),
    }

    return ReagraphDiff(nodes=tuple(nodes), edges=tuple(edges), counts=counts)
