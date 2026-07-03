"""Merge a one/two-hop expansion into an existing graph payload (§17.8).

Слияние результата раскрытия соседей (expansion) в уже показанный граф без
сброса раскладки (без reset layout, §17.8): пользователь кликает узел, фронтенд
запрашивает +1/+2 hop и подмешивает *новые* узлы/рёбра к тому, что уже на экране.
Существующие узлы (их координаты/props/layout) при этом сохраняются как есть.

Both ``base`` and ``expansion`` are §5.3 ``GraphResponse`` payloads — plain dicts
``{"nodes": [ {"id": …, …}, … ], "edges": [ {"id": …, …}, … ]}``. The merge is a
pure, deterministic function (no DB, no I/O): it dedups nodes by ``id`` and edges by
``id``, keeping the *base* copy of anything already present so existing layout/props
survive, and appending only genuinely-new items after the base ones.

``prefer`` selects the winner for a shared id:

- ``prefer="base"`` (default) — the shared id keeps the base dict verbatim (its layout
  is preserved) and is NOT counted as added;
- ``prefer="expansion"`` — the shared id is overwritten with the expansion dict (still
  not counted as added, since the id already existed in base).

Only ids present *solely* in the expansion are appended and recorded in
``added_node_ids`` / ``added_edge_ids``.

Kuzu note: custom node props are NOT queryable columns — a retriever RETURNs base
columns and reads the rest via ``get_node``; by the time node/edge dicts reach this
module they already carry merged props, so nothing here touches the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Accepted values for the ``prefer`` keyword: which side wins a shared id (§17.8).
_PREFER_BASE = "base"
_PREFER_EXPANSION = "expansion"
_VALID_PREFER: frozenset[str] = frozenset({_PREFER_BASE, _PREFER_EXPANSION})


@dataclass(frozen=True)
class MergedGraph:
    """Result of merging an expansion into a base graph payload (§17.8).

    ``nodes`` / ``edges`` are the deduped, merged items — base items first, then the
    newly-added ones in expansion order. ``added_node_ids`` / ``added_edge_ids`` list
    the ids that existed *only* in the expansion (i.e. truly new to the view).
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    added_node_ids: tuple[str, ...]
    added_edge_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready view with camelCase ``addedNodeIds`` / ``addedEdgeIds`` (§5.3)."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "addedNodeIds": list(self.added_node_ids),
            "addedEdgeIds": list(self.added_edge_ids),
        }


def _merge_items(
    base_items: list[dict[str, Any]],
    expansion_items: list[dict[str, Any]],
    *,
    prefer: str,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Dedup ``base_items`` + ``expansion_items`` by ``id`` (§17.8).

    Returns ``(merged, added_ids)``: base items come first (optionally overwritten by
    their expansion twin when ``prefer="expansion"``), then items whose id is new to
    the base, in expansion order. ``added_ids`` are those new-only ids. Items without
    an ``id`` are dropped (they cannot be deduped or referenced by layout).
    """
    expansion_by_id: dict[str, dict[str, Any]] = {}
    for item in expansion_items:
        item_id = item.get("id")
        if item_id is None:
            continue
        # First occurrence wins within the expansion side (stable, deterministic).
        expansion_by_id.setdefault(str(item_id), item)

    merged: list[dict[str, Any]] = []
    base_ids: set[str] = set()
    for item in base_items:
        item_id = item.get("id")
        if item_id is None:
            continue
        item_id = str(item_id)
        if item_id in base_ids:
            continue  # dedup repeated ids inside the base side, keep the first
        base_ids.add(item_id)
        if prefer == _PREFER_EXPANSION and item_id in expansion_by_id:
            merged.append(expansion_by_id[item_id])
        else:
            merged.append(item)

    added_ids: list[str] = []
    seen_added: set[str] = set()
    for item in expansion_items:
        item_id = item.get("id")
        if item_id is None:
            continue
        item_id = str(item_id)
        if item_id in base_ids or item_id in seen_added:
            continue
        seen_added.add(item_id)
        added_ids.append(item_id)
        merged.append(expansion_by_id[item_id])

    return tuple(merged), tuple(added_ids)


def merge_graph(
    base: dict[str, Any],
    expansion: dict[str, Any],
    *,
    prefer: str = _PREFER_BASE,
) -> MergedGraph:
    """Merge an ``expansion`` §5.3 payload into ``base`` without resetting layout (§17.8).

    ``base`` / ``expansion`` are ``{"nodes": [...], "edges": [...]}`` dicts (missing
    keys read as empty). Nodes dedup by ``id``, edges by ``id``. With the default
    ``prefer="base"`` a shared id keeps the base dict (its layout/props survive) and is
    not counted as added; ``prefer="expansion"`` overwrites the shared item with the
    expansion dict. Ids present only in the expansion are appended after the base items
    and recorded in ``added_node_ids`` / ``added_edge_ids``.
    """
    if prefer not in _VALID_PREFER:
        raise ValueError(f"prefer must be one of {sorted(_VALID_PREFER)}, got {prefer!r}")

    base_nodes: list[dict[str, Any]] = list(base.get("nodes", []))
    base_edges: list[dict[str, Any]] = list(base.get("edges", []))
    exp_nodes: list[dict[str, Any]] = list(expansion.get("nodes", []))
    exp_edges: list[dict[str, Any]] = list(expansion.get("edges", []))

    nodes, added_node_ids = _merge_items(base_nodes, exp_nodes, prefer=prefer)
    edges, added_edge_ids = _merge_items(base_edges, exp_edges, prefer=prefer)

    return MergedGraph(
        nodes=nodes,
        edges=edges,
        added_node_ids=added_node_ids,
        added_edge_ids=added_edge_ids,
    )
