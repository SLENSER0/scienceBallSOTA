"""Graph Explorer legend visibility toggle filter (§17.8).

RU: Применяет переключатели видимости легенды графа (:class:`GraphLegend`) к
конкретному графу, скрывая категории узлов/рёбер и классы кодирования (§17.8).
``build_legend`` выдаёт лишь статический дескриптор; применение переключателей к
графу до сих пор не реализовано. :func:`apply_visibility` принимает граф
(``dict`` с ключами ``nodes`` и ``edges``) и замороженное
:class:`VisibilityState` и возвращает :class:`FilteredGraph`:

* узлы, чей ``type`` входит в ``hidden_node_types``, удаляются вместе со всеми
  инцидентными рёбрами;
* рёбра, чей ``type`` входит в ``hidden_edge_types``, удаляются (их концевые
  узлы сохраняются);
* при ``show_inferred=False`` удаляются рёбра с ``inferred=True``;
* при ``show_contradicted=False`` удаляются рёбра с ``contradicted=True``.

Счётчики ``hidden_node_count`` / ``hidden_edge_count`` считают удалённые узлы и
рёбра (включая рёбра, инцидентные скрытым узлам).

EN: Applies Graph Explorer legend visibility toggles (:class:`GraphLegend`) to a
concrete graph, hiding node/edge categories and encoding classes (§17.8).
``build_legend`` only emits a static descriptor; applying toggles to a graph was
previously unbuilt. :func:`apply_visibility` takes a graph (``dict`` with
``nodes`` and ``edges`` keys) plus a frozen :class:`VisibilityState` and returns
a :class:`FilteredGraph`:

* nodes whose ``type`` is in ``hidden_node_types`` are dropped together with all
  their incident edges;
* edges whose ``type`` is in ``hidden_edge_types`` are dropped (their endpoint
  nodes are kept);
* when ``show_inferred=False`` edges with ``inferred=True`` are dropped;
* when ``show_contradicted=False`` edges with ``contradicted=True`` are dropped.

The ``hidden_node_count`` / ``hidden_edge_count`` counters tally removed nodes
and edges (including edges incident to hidden nodes).

Pure python — no store access. Node ids are read from a node's ``id`` key; edge
endpoints from ``source`` / ``target`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# §17.8 node dict keys read by :func:`apply_visibility`.
NODE_ID_KEY = "id"
NODE_TYPE_KEY = "type"

# §17.8 edge dict keys read by :func:`apply_visibility`.
EDGE_TYPE_KEY = "type"
EDGE_SOURCE_KEY = "source"
EDGE_TARGET_KEY = "target"
EDGE_INFERRED_KEY = "inferred"
EDGE_CONTRADICTED_KEY = "contradicted"


@dataclass(frozen=True)
class VisibilityState:
    """Frozen legend visibility toggle state (§17.8).

    ``hidden_node_types`` / ``hidden_edge_types`` are the node/edge ``type``
    categories toggled off in the legend. ``show_inferred`` and
    ``show_contradicted`` are encoding-class toggles: when ``False`` they hide
    edges flagged ``inferred`` / ``contradicted`` respectively. The neutral
    default ``VisibilityState((), (), True, True)`` hides nothing.
    """

    hidden_node_types: tuple[str, ...] = ()
    hidden_edge_types: tuple[str, ...] = ()
    show_inferred: bool = True
    show_contradicted: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of this visibility state (§17.8)."""
        return {
            "hidden_node_types": list(self.hidden_node_types),
            "hidden_edge_types": list(self.hidden_edge_types),
            "show_inferred": self.show_inferred,
            "show_contradicted": self.show_contradicted,
        }


@dataclass(frozen=True)
class FilteredGraph:
    """Frozen result of applying visibility toggles to a graph (§17.8).

    ``nodes`` / ``edges`` are the surviving node/edge dicts (order preserved).
    ``hidden_node_count`` / ``hidden_edge_count`` count how many nodes/edges were
    removed relative to the input graph.
    """

    nodes: tuple[dict, ...]
    edges: tuple[dict, ...]
    hidden_node_count: int
    hidden_edge_count: int

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the filtered graph (§17.8)."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "hidden_node_count": self.hidden_node_count,
            "hidden_edge_count": self.hidden_edge_count,
        }


def apply_visibility(graph: dict, state: VisibilityState) -> FilteredGraph:
    """Apply legend visibility toggles to ``graph`` (§17.8).

    RU: Возвращает :class:`FilteredGraph` со скрытыми категориями узлов/рёбер.
    EN: Returns a :class:`FilteredGraph` with hidden node/edge categories.

    A node is dropped when its ``type`` is in ``state.hidden_node_types``. An
    edge is dropped when its ``type`` is in ``state.hidden_edge_types``, when it
    is incident to a dropped node, when it is ``inferred`` while
    ``show_inferred`` is ``False``, or when it is ``contradicted`` while
    ``show_contradicted`` is ``False``. Edges dropped for any reason count once
    toward ``hidden_edge_count``.
    """
    nodes = list(graph.get("nodes", ()))
    edges = list(graph.get("edges", ()))

    hidden_node_types = frozenset(state.hidden_node_types)
    hidden_edge_types = frozenset(state.hidden_edge_types)

    kept_nodes: list[dict] = []
    hidden_node_ids: set[Any] = set()
    for node in nodes:
        if node.get(NODE_TYPE_KEY) in hidden_node_types:
            hidden_node_ids.add(node.get(NODE_ID_KEY))
        else:
            kept_nodes.append(node)

    kept_edges: list[dict] = []
    hidden_edge_count = 0
    for edge in edges:
        if _edge_hidden(edge, hidden_edge_types, hidden_node_ids, state):
            hidden_edge_count += 1
        else:
            kept_edges.append(edge)

    return FilteredGraph(
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        hidden_node_count=len(nodes) - len(kept_nodes),
        hidden_edge_count=hidden_edge_count,
    )


def _edge_hidden(
    edge: dict,
    hidden_edge_types: frozenset[str],
    hidden_node_ids: set[Any],
    state: VisibilityState,
) -> bool:
    """Return ``True`` when ``edge`` must be hidden under ``state`` (§17.8)."""
    if edge.get(EDGE_TYPE_KEY) in hidden_edge_types:
        return True
    if edge.get(EDGE_SOURCE_KEY) in hidden_node_ids:
        return True
    if edge.get(EDGE_TARGET_KEY) in hidden_node_ids:
        return True
    if not state.show_inferred and edge.get(EDGE_INFERRED_KEY) is True:
        return True
    return not state.show_contradicted and edge.get(EDGE_CONTRADICTED_KEY) is True
