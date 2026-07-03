"""Graph Explorer category-toggle filter over §5.3 GraphResponse (§17.8 / §17.16).

Экран Graph Explorer рисует легенду (`GraphLegend`, §5.2.3) с переключателями
видимости по типам узлов и рёбер. When a user hides a category, the frontend must
render the graph без скрытых узлов/рёбер, а также без «повисших» рёбер, чей узел-
эндпоинт был убран. This module is the pure, offline transform that applies those
visibility toggles to an already-encoded §5.3 ``GraphResponse`` dict.

Contract (§5.3 payload shapes):
  * node dict carries at least ``id`` and ``type`` (§5.3 ``GraphNode``);
  * edge dict carries at least ``id``, ``source``, ``target`` and ``type``
    (§5.3 ``GraphEdge``); ``source``/``target`` reference node ``id`` values.

An edge is dropped when *either* its ``type`` is hidden *or* one of its endpoints
was dropped (orphan edge). Hidden counts tally everything removed for any reason.
Deterministic, no I/O, no clock — safe to call inside request handlers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FilteredGraph:
    """Result of applying §5.2.3 legend toggles to a §5.3 GraphResponse.

    ``nodes``/``edges`` — сохранившиеся элементы (в исходном порядке); hidden
    counts — сколько узлов/рёбер было убрано (для любой причины).
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    hidden_node_count: int
    hidden_edge_count: int

    def as_dict(self) -> dict[str, Any]:
        """Serialize to the frontend JSON shape (camelCase per §5.3)."""
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "hiddenNodeCount": self.hidden_node_count,
            "hiddenEdgeCount": self.hidden_edge_count,
        }


def apply_category_filter(
    payload: dict[str, Any],
    hidden_node_types: set[str] = frozenset(),  # type: ignore[assignment]
    hidden_edge_types: set[str] = frozenset(),  # type: ignore[assignment]
) -> FilteredGraph:
    """Apply §5.2.3 category-visibility toggles to a §5.3 GraphResponse dict.

    Скрываем узлы, чей ``type`` попал в ``hidden_node_types``; скрываем рёбра, чей
    ``type`` попал в ``hidden_edge_types`` ИЛИ чей эндпоинт (``source``/``target``)
    был убран вместе с узлом. Returns kept nodes/edges plus removal counts.
    """
    raw_nodes: list[dict[str, Any]] = list(payload.get("nodes") or [])
    raw_edges: list[dict[str, Any]] = list(payload.get("edges") or [])

    kept_nodes: list[dict[str, Any]] = []
    surviving_ids: set[str] = set()
    for node in raw_nodes:
        if node.get("type") in hidden_node_types:
            continue
        kept_nodes.append(node)
        surviving_ids.add(node.get("id"))

    kept_edges: list[dict[str, Any]] = []
    for edge in raw_edges:
        if edge.get("type") in hidden_edge_types:
            continue
        if edge.get("source") not in surviving_ids:
            continue
        if edge.get("target") not in surviving_ids:
            continue
        kept_edges.append(edge)

    return FilteredGraph(
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        hidden_node_count=len(raw_nodes) - len(kept_nodes),
        hidden_edge_count=len(raw_edges) - len(kept_edges),
    )


def apply_category_filter_json(
    payload: dict[str, Any],
    hidden_node_types: set[str] = frozenset(),  # type: ignore[assignment]
    hidden_edge_types: set[str] = frozenset(),  # type: ignore[assignment]
) -> str:
    """Convenience: filter then ``json.dumps`` the frontend payload (§5.3)."""
    result = apply_category_filter(payload, hidden_node_types, hidden_edge_types)
    return json.dumps(result.as_dict())
