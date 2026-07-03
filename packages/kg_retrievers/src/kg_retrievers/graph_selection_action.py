"""Lasso/box selection → subgraph + ask-agent context (§17.8).

Экран Graph Explorer позволяет пользователю обвести лассо/рамкой набор узлов и
затем открыть панель действий: «показать подграф» и «спросить агента про выделенный
подграф». This module is the pure, client-side builder for that action panel — it
takes an already-loaded §5.3 ``GraphResponse`` dict plus the explicit set of selected
node ids, and returns the induced subgraph together with an ``ask_context`` payload
ready to hand to the agent.

Отличия от смежных модулей:
  * ``subgraph_extract.induced_subgraph`` — store-backed (Kuzu), тянет узлы/рёбра из
    графа; здесь же вход — уже отрисованный §5.3 dict, без Kuzu и без I/O;
  * ``graph_category_filter`` — прячет по *типу* элемента; здесь выбор задаётся явным
    множеством id, и дополнительно формируется контекст для запроса к агенту.

Contract (§5.3 payload shapes):
  * node dict carries at least ``id`` and ``type`` (§5.3 ``GraphNode``);
    an optional ``label`` is surfaced into ``ask_context``;
  * edge dict carries ``source``/``target`` referencing node ``id`` values.

An edge survives only when *both* endpoints are selected — orphan/external edges
(один эндпоинт вне выделения) отбрасываются. Deterministic, no I/O, no clock.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SelectionSubgraph:
    """Induced subgraph of a lasso/box selection plus ask-agent context (§17.8).

    ``nodes``/``edges`` — сохранившиеся элементы (в исходном порядке §5.3);
    ``ask_context`` — компактная сводка выделения для запроса к агенту.
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    ask_context: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialize to the frontend JSON shape (camelCase per §5.3)."""
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "askContext": dict(self.ask_context),
        }


def select_subgraph(
    graph: dict[str, Any],
    selected_ids: Iterable[str],
) -> SelectionSubgraph:
    """Build the §17.8 selection subgraph from a §5.3 GraphResponse dict.

    Оставляем только узлы, чей ``id`` попал в ``selected_ids``, и только рёбра, у
    которых ОБА эндпоинта (``source`` и ``target``) выделены; повисшие/внешние рёбра
    отбрасываются. Additionally emit ``ask_context`` describing the selection so the
    frontend can «спросить агента про выделенный подграф».
    """
    selection: set[str] = set(selected_ids)
    raw_nodes: list[dict[str, Any]] = list(graph.get("nodes") or [])
    raw_edges: list[dict[str, Any]] = list(graph.get("edges") or [])

    kept_nodes: list[dict[str, Any]] = [node for node in raw_nodes if node.get("id") in selection]
    kept_edges: list[dict[str, Any]] = [
        edge
        for edge in raw_edges
        if edge.get("source") in selection and edge.get("target") in selection
    ]

    node_ids: list[str] = [node.get("id") for node in kept_nodes]
    labels: list[str] = [node.get("label", node.get("id")) for node in kept_nodes]
    types: dict[str, int] = dict(Counter(node.get("type") for node in kept_nodes))

    ask_context: dict[str, Any] = {
        "nodeIds": sorted(node_ids),
        "labels": labels,
        "types": types,
        "nodeCount": len(kept_nodes),
        "edgeCount": len(kept_edges),
    }

    return SelectionSubgraph(
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        ask_context=ask_context,
    )
