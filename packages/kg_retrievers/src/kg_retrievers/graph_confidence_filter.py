"""GlobalFilters confidence/verified pruning over a §5.3 GraphResponse (§17.5 / §2.1).

§17.5 задаёт `GlobalFilters` — глобальные фильтры выдачи: ``min_confidence`` (порог
достоверности) и ``verified_only`` (только проверенные факты). This module is the pure,
offline transform that applies those two filters to an already-loaded §5.3
``GraphResponse`` dict. It complements ``graph_category_filter`` — that one prunes purely
by node/edge *type*; this one prunes by *confidence* and *verification* status и затем
убирает «повисшие» рёбра, чей эндпоинт был отфильтрован.

Contract (§5.3 payload shapes):
  * node dict carries at least ``id`` (§5.3 ``GraphNode``); optional ``confidence``
    (float|None) and ``verified`` (truthy flag);
  * edge dict carries at least ``id``, ``source``, ``target`` (§5.3 ``GraphEdge``);
    optional ``confidence``; ``source``/``target`` reference node ``id`` values.

Pruning rules (§17.5):
  * an element with ``confidence`` == ``None`` is kept — unknown passes the threshold
    (мы не отбрасываем факт лишь потому, что достоверность не посчитана);
  * a node is dropped when its ``confidence`` is *below* ``min_confidence`` OR when
    ``verified_only`` is set and its ``verified`` flag is falsy;
  * an edge is dropped when its ``confidence`` is *below* ``min_confidence`` OR when one
    of its endpoints was dropped (orphan edge);
  * ``dropped_nodes`` / ``dropped_edges`` tally everything removed for any reason.

Deterministic, no I/O, no clock — safe to call inside request handlers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrunedGraph:
    """Result of applying §17.5 GlobalFilters to a §5.3 GraphResponse.

    ``nodes``/``edges`` — сохранившиеся элементы (в исходном порядке); dropped counts —
    сколько узлов/рёбер было убрано (по достоверности, проверке или как orphan).
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    dropped_nodes: int
    dropped_edges: int

    def as_dict(self) -> dict[str, Any]:
        """Serialize to the frontend JSON shape (camelCase per §5.3)."""
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "droppedNodes": self.dropped_nodes,
            "droppedEdges": self.dropped_edges,
        }


def _below_threshold(confidence: Any, min_confidence: float | None) -> bool:
    """True when ``confidence`` fails the §17.5 ``min_confidence`` gate.

    ``None`` (неизвестно) всегда проходит; порог не задан — тоже проходит.
    """
    if min_confidence is None:
        return False
    if confidence is None:
        return False
    return float(confidence) < min_confidence


def prune_graph(
    graph: dict[str, Any],
    *,
    min_confidence: float | None = None,
    verified_only: bool = False,
) -> PrunedGraph:
    """Apply §17.5 GlobalFilters (min_confidence / verified_only) to a §5.3 GraphResponse.

    Убираем узлы ниже порога достоверности или (при ``verified_only``) непроверенные;
    убираем рёбра ниже порога или «повисшие» после удаления узла. Returns kept
    nodes/edges plus exact removal counts. ``confidence == None`` treated as unknown-pass.
    """
    raw_nodes: list[dict[str, Any]] = list(graph.get("nodes") or [])
    raw_edges: list[dict[str, Any]] = list(graph.get("edges") or [])

    kept_nodes: list[dict[str, Any]] = []
    surviving_ids: set[Any] = set()
    for node in raw_nodes:
        if _below_threshold(node.get("confidence"), min_confidence):
            continue
        if verified_only and not node.get("verified"):
            continue
        kept_nodes.append(node)
        surviving_ids.add(node.get("id"))

    kept_edges: list[dict[str, Any]] = []
    for edge in raw_edges:
        if _below_threshold(edge.get("confidence"), min_confidence):
            continue
        if edge.get("source") not in surviving_ids:
            continue
        if edge.get("target") not in surviving_ids:
            continue
        kept_edges.append(edge)

    return PrunedGraph(
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        dropped_nodes=len(raw_nodes) - len(kept_nodes),
        dropped_edges=len(raw_edges) - len(kept_edges),
    )


def prune_graph_json(
    graph: dict[str, Any],
    *,
    min_confidence: float | None = None,
    verified_only: bool = False,
) -> str:
    """Convenience: prune then ``json.dumps`` the frontend payload (§5.3)."""
    result = prune_graph(graph, min_confidence=min_confidence, verified_only=verified_only)
    return json.dumps(result.as_dict())
