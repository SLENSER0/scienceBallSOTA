"""Graph version diff — added / removed / changed (§16.10).

Compare two *snapshots* of the knowledge graph (версия графа / graph version) and
report what changed between them (добавлено / удалено / изменено):

- new and dropped nodes (``added_nodes`` / ``removed_nodes``);
- per-field deltas for surviving nodes (``changed_nodes`` — id → {field: [old, new]});
- new and dropped edges (``added_edges`` / ``removed_edges``).

A *snapshot* is a plain dict ``{"nodes": {id: props}, "edges": {edge_key: props}}``.
The diff core (:func:`diff_snapshots`) is pure Python and has no store dependency, so
hand-made snapshots diff exactly the same way as ones read from a live store.

:func:`snapshot_store` reads a :class:`~kg_retrievers.graph_store.KuzuGraphStore` into
that shape, keeping only *stable comparable* node fields (see :data:`STABLE_NODE_FIELDS`)
so that volatile bookkeeping (timestamps, run ids, pagerank …) never shows up as a
spurious change. This module is read-only: it never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Node fields that are meaningful to compare across versions (§16.10). Everything
# else (timestamps, extractor_run_id, degree, pagerank …) is bookkeeping and is
# deliberately excluded so it cannot register as a false "changed" delta.
STABLE_NODE_FIELDS: tuple[str, ...] = (
    "name",
    "review_status",
    "verified",
    "value_normalized",
    "confidence",
)

# Edge fields carried into a snapshot; edges diff by key only (added / removed).
STABLE_EDGE_FIELDS: tuple[str, ...] = ("type", "confidence")


@dataclass(frozen=True)
class GraphDiff:
    """Structured difference between two graph versions (§16.10).

    ``added_nodes`` / ``removed_nodes`` map node id → its snapshot props.
    ``changed_nodes`` maps node id → {field: [old, new]} for every field whose
    value differs (a missing field on either side reads as ``None``).
    ``added_edges`` / ``removed_edges`` map edge key → its snapshot props.
    """

    added_nodes: dict[str, dict[str, Any]]
    removed_nodes: dict[str, dict[str, Any]]
    changed_nodes: dict[str, dict[str, list[Any]]]
    added_edges: dict[str, dict[str, Any]]
    removed_edges: dict[str, dict[str, Any]]

    @property
    def is_empty(self) -> bool:
        """True when the two versions are identical (nothing added/removed/changed)."""
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.changed_nodes
            or self.added_edges
            or self.removed_edges
        )

    @property
    def node_change_count(self) -> int:
        """Total nodes touched: added + removed + changed."""
        return len(self.added_nodes) + len(self.removed_nodes) + len(self.changed_nodes)

    @property
    def edge_change_count(self) -> int:
        """Total edges touched: added + removed."""
        return len(self.added_edges) + len(self.removed_edges)

    def as_dict(self) -> dict:
        """JSON-serialisable view of the diff (§16.10)."""
        return {
            "added_nodes": dict(self.added_nodes),
            "removed_nodes": dict(self.removed_nodes),
            "changed_nodes": {k: dict(v) for k, v in self.changed_nodes.items()},
            "added_edges": dict(self.added_edges),
            "removed_edges": dict(self.removed_edges),
            "is_empty": self.is_empty,
            "node_change_count": self.node_change_count,
            "edge_change_count": self.edge_change_count,
        }


def _field_delta(
    before_props: dict[str, Any],
    after_props: dict[str, Any],
) -> dict[str, list[Any]]:
    """Per-field ``{field: [old, new]}`` for every differing field (§16.10).

    Keys are the union of both sides, visited in sorted order for determinism; a
    field absent on one side compares as ``None``.
    """
    delta: dict[str, list[Any]] = {}
    for key in sorted(set(before_props) | set(after_props)):
        old = before_props.get(key)
        new = after_props.get(key)
        if old != new:
            delta[key] = [old, new]
    return delta


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> GraphDiff:
    """Diff two graph snapshots into a :class:`GraphDiff` (§16.10).

    ``before`` / ``after`` are ``{"nodes": {id: props}, "edges": {key: props}}``
    dicts (missing keys treated as empty). Pure Python — no store required.
    """
    before_nodes: dict[str, dict[str, Any]] = before.get("nodes", {})
    after_nodes: dict[str, dict[str, Any]] = after.get("nodes", {})
    before_edges: dict[str, dict[str, Any]] = before.get("edges", {})
    after_edges: dict[str, dict[str, Any]] = after.get("edges", {})

    added_nodes = {nid: after_nodes[nid] for nid in sorted(after_nodes) if nid not in before_nodes}
    removed_nodes = {
        nid: before_nodes[nid] for nid in sorted(before_nodes) if nid not in after_nodes
    }
    changed_nodes: dict[str, dict[str, list[Any]]] = {}
    for nid in sorted(set(before_nodes) & set(after_nodes)):
        delta = _field_delta(before_nodes[nid], after_nodes[nid])
        if delta:
            changed_nodes[nid] = delta

    added_edges = {k: after_edges[k] for k in sorted(after_edges) if k not in before_edges}
    removed_edges = {k: before_edges[k] for k in sorted(before_edges) if k not in after_edges}

    return GraphDiff(
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        changed_nodes=changed_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
    )


def edge_key(src: str, rel_type: str, dst: str) -> str:
    """Stable edge identifier ``src|type|dst`` used as a snapshot key (§16.10)."""
    return f"{src}|{rel_type}|{dst}"


def _stable_node_props(node: dict[str, Any]) -> dict[str, Any]:
    """Keep only present :data:`STABLE_NODE_FIELDS` from a node dict."""
    return {f: node[f] for f in STABLE_NODE_FIELDS if f in node}


def snapshot_store(
    store: KuzuGraphStore,
    node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Read a :class:`KuzuGraphStore` into a diffable snapshot dict (§16.10).

    When ``node_ids`` is ``None`` every ``Node`` is captured; otherwise only the
    given ids (missing ones are silently skipped). Node props are limited to
    :data:`STABLE_NODE_FIELDS`. Edges are captured only between captured nodes,
    keyed by :func:`edge_key`.
    """
    if node_ids is None:
        ids = [r[0] for r in store.rows("MATCH (n:Node) RETURN n.id ORDER BY n.id")]
    else:
        ids = list(node_ids)

    nodes: dict[str, dict[str, Any]] = {}
    for nid in ids:
        nd = store.get_node(nid)
        if nd is not None:
            nodes[nid] = _stable_node_props(nd)
    captured = set(nodes)

    edges: dict[str, dict[str, Any]] = {}
    rows = store.rows("MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id, r.confidence")
    for src, rel_type, dst, conf in rows:
        if src not in captured or dst not in captured:
            continue
        props: dict[str, Any] = {"type": rel_type}
        if conf is not None:
            props["confidence"] = conf
        edges[edge_key(src, rel_type, dst)] = props

    return {"nodes": nodes, "edges": edges}


def diff_store_snapshots(
    before_store: KuzuGraphStore,
    after_store: KuzuGraphStore,
    node_ids: list[str] | None = None,
) -> GraphDiff:
    """Snapshot two stores and diff them (§16.10).

    Convenience wrapper: :func:`snapshot_store` each store (over the same optional
    ``node_ids`` scope), then :func:`diff_snapshots`.
    """
    before = snapshot_store(before_store, node_ids)
    after = snapshot_store(after_store, node_ids)
    return diff_snapshots(before, after)
