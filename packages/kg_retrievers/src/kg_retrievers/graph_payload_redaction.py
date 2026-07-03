"""Graph-payload row-level access redaction (§19.3).

RU: Построчная редакция графового payload по правам доступа (§19.3). Функция
:func:`redact_graph_payload` принимает payload графа (``nodes`` / ``edges``) и
множество разрешённых ``source_id`` (:class:`frozenset`), затем возвращает НОВЫЙ
payload, из которого удалены узлы с заданным, но неразрешённым ``source_id``, а
также рёбра, ссылающиеся на удалённый узел (по ``source`` / ``target``). Узлы
без ``source_id`` (только схема) сохраняются. Оригинальный payload не мутируется.
Итог сопровождается отчётом :class:`RedactionReport` со счётчиками и отсортированным
списком скрытых источников.

EN: Row-level access redaction for a graph payload (§19.3). :func:`redact_graph_payload`
takes a graph payload (``nodes`` / ``edges``) and a frozenset of allowed
``source_id`` values, and returns a NEW payload dropping nodes whose ``source_id``
is set and not allowed, plus edges that reference any dropped node id (via
``source`` / ``target``). Nodes with no ``source_id`` (schema-only) are retained.
The original payload is never mutated. A :class:`RedactionReport` accompanies the
result with kept/hidden counts and the sorted distinct hidden source ids.

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read ``source_id`` via ``get_node()``
before assembling the payload passed here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# §19.3 payload keys.
NODES_KEY = "nodes"
EDGES_KEY = "edges"
NODE_ID_KEY = "id"
SOURCE_ID_KEY = "source_id"
EDGE_SOURCE_KEY = "source"
EDGE_TARGET_KEY = "target"


@dataclass(frozen=True)
class RedactionReport:
    """Frozen summary of a row-level redaction pass (§19.3).

    ``kept_nodes`` / ``kept_edges`` count retained elements; ``hidden_nodes`` /
    ``hidden_edges`` count removed elements; ``hidden_source_ids`` is the sorted
    tuple of distinct ``source_id`` values that caused node removal.
    """

    kept_nodes: int
    kept_edges: int
    hidden_nodes: int
    hidden_edges: int
    hidden_source_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§19.3, house style)."""
        return {
            "kept_nodes": self.kept_nodes,
            "kept_edges": self.kept_edges,
            "hidden_nodes": self.hidden_nodes,
            "hidden_edges": self.hidden_edges,
            "hidden_source_ids": list(self.hidden_source_ids),
        }


def _node_allowed(node: Mapping[str, Any], allowed_source_ids: frozenset[str]) -> bool:
    """Decide whether ``node`` survives redaction for ``allowed_source_ids`` (§19.3).

    A node with no ``source_id`` (or a falsy one) is schema-only and always kept.
    Otherwise it is kept iff its ``source_id`` is in ``allowed_source_ids``.
    """
    source_id = node.get(SOURCE_ID_KEY)
    if not source_id:
        return True  # Schema-only node — no row-level source to gate on.
    return source_id in allowed_source_ids


def redact_graph_payload(
    payload: Mapping[str, Any],
    allowed_source_ids: frozenset[str],
) -> tuple[dict[str, Any], RedactionReport]:
    """Redact ``payload`` to rows visible under ``allowed_source_ids`` (§19.3).

    Returns a NEW payload plus a :class:`RedactionReport`. Nodes whose
    ``source_id`` is set and not allowed are dropped; nodes with no ``source_id``
    are retained. Edges are dropped when they reference any dropped node id via
    ``source`` or ``target``. The input ``payload`` is never mutated: retained
    nodes and edges are shallow-copied into fresh ``dict`` objects.
    """
    nodes = list(payload.get(NODES_KEY, ()))
    edges = list(payload.get(EDGES_KEY, ()))

    kept_nodes: list[dict[str, Any]] = []
    dropped_node_ids: set[Any] = set()
    hidden_sources: set[str] = set()
    hidden_nodes = 0
    for node in nodes:
        if _node_allowed(node, allowed_source_ids):
            kept_nodes.append(dict(node))
        else:
            hidden_nodes += 1
            dropped_node_ids.add(node.get(NODE_ID_KEY))
            hidden_sources.add(node[SOURCE_ID_KEY])

    kept_edges: list[dict[str, Any]] = []
    hidden_edges = 0
    for edge in edges:
        src = edge.get(EDGE_SOURCE_KEY)
        tgt = edge.get(EDGE_TARGET_KEY)
        if src in dropped_node_ids or tgt in dropped_node_ids:
            hidden_edges += 1
        else:
            kept_edges.append(dict(edge))

    report = RedactionReport(
        kept_nodes=len(kept_nodes),
        kept_edges=len(kept_edges),
        hidden_nodes=hidden_nodes,
        hidden_edges=hidden_edges,
        hidden_source_ids=tuple(sorted(hidden_sources)),
    )
    new_payload = {NODES_KEY: kept_nodes, EDGES_KEY: kept_edges}
    return new_payload, report
