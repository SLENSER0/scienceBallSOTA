"""Глобальные фильтры графа: URL-параметры и предикат над ``GraphResponse`` (§17.5).

Каноническое состояние глобального фильтра графа из §17.5. Одно неизменяемое
:class:`GraphFilterState` одновременно сериализуется в query-параметры URL
(:meth:`GraphFilterState.to_query_params`) и применяется как предикат над узлами
``GraphResponse`` (:func:`node_matches`, :func:`apply_graph_filter`). Фасеты,
``gap_filter`` и ``experiment_filters`` живут в других модулях; общего фильтра по
узлам/рёбрам графа до сих пор не существовало.

Canonical global graph-filter state from §17.5. A single frozen
:class:`GraphFilterState` both serialises to URL query-parameters
(:meth:`GraphFilterState.to_query_params`) and applies as a predicate over the
nodes of a ``GraphResponse`` (:func:`node_matches`, :func:`apply_graph_filter`).
Facets, ``gap_filter`` and ``experiment_filters`` are scoped elsewhere; no
generic graph node/edge filter existed before.

* :class:`GraphFilterState` — неизменяемое состояние фильтра с :meth:`as_dict`
  и :meth:`to_query_params` / immutable filter state.
* :func:`node_matches` — узел + состояние → ``bool`` / node predicate.
* :func:`apply_graph_filter` — граф + состояние → отфильтрованный граф / filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GraphFilterState:
    """Неизменяемое каноническое состояние глобального фильтра графа (§17.5).

    Immutable canonical global graph-filter state (§17.5). Пустые кортежи и
    значения по умолчанию (``min_confidence`` 0.0, ``verified_only`` False,
    ``date_from`` None) означают «фильтр неактивен» и опускаются в
    :meth:`to_query_params`.

    Empty tuples and the defaults (``min_confidence`` 0.0, ``verified_only``
    False, ``date_from`` None) mean "filter inactive" and are omitted from
    :meth:`to_query_params`.
    """

    node_types: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    labs: tuple[str, ...] = ()
    min_confidence: float = 0.0
    verified_only: bool = False
    date_from: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Полное структурное представление состояния / full wire form (§17.5).

        Все поля присутствуют всегда; кортежи отдаются списками. Служит для
        отладки и передачи состояния целиком, в отличие от компактного
        :meth:`to_query_params`.
        """
        return {
            "node_types": list(self.node_types),
            "sources": list(self.sources),
            "labs": list(self.labs),
            "min_confidence": self.min_confidence,
            "verified_only": self.verified_only,
            "date_from": self.date_from,
        }

    def to_query_params(self) -> dict[str, str]:
        """Сериализовать активные поля в query-параметры URL (§17.5).

        Serialise only the active fields into URL query-parameters. Пустые
        кортежи и значения по умолчанию опускаются; кортежи склеиваются через
        ``','``. Ключи: ``nodeTypes``, ``sources``, ``labs``, ``minConfidence``,
        ``verifiedOnly``, ``dateFrom``.
        """
        params: dict[str, str] = {}
        if self.node_types:
            params["nodeTypes"] = ",".join(self.node_types)
        if self.sources:
            params["sources"] = ",".join(self.sources)
        if self.labs:
            params["labs"] = ",".join(self.labs)
        if self.min_confidence:
            params["minConfidence"] = str(self.min_confidence)
        if self.verified_only:
            params["verifiedOnly"] = "true"
        if self.date_from is not None:
            params["dateFrom"] = self.date_from
        return params


def node_matches(state: GraphFilterState, node: dict[str, Any]) -> bool:
    """Проверить один узел графа против состояния фильтра (§17.5).

    Test one graph node against the filter state. Каждое активное поле —
    отдельное условие И (AND); неактивные поля пропускаются.

    * ``node_types`` (непустой) — ``node['type']`` обязан входить в кортеж.
    * ``sources`` (непустой) — ``node['source']`` обязан входить в кортеж.
    * ``labs`` (непустой) — ``node['lab']`` обязан входить в кортеж.
    * ``min_confidence`` (> 0) — ``node['confidence']`` (по умолчанию 0.0)
      обязан быть ``>=`` порога.
    * ``verified_only`` (True) — ``node['verified']`` обязан быть истинным.
    * ``date_from`` (задан) — ``node['date']`` обязан лексикографически быть
      ``>=`` значения (ISO-даты сравниваются как строки); без даты — отказ.
    """
    if state.node_types and node.get("type") not in state.node_types:
        return False
    if state.sources and node.get("source") not in state.sources:
        return False
    if state.labs and node.get("lab") not in state.labs:
        return False
    if state.min_confidence and float(node.get("confidence", 0.0)) < state.min_confidence:
        return False
    if state.verified_only and not node.get("verified", False):
        return False
    if state.date_from is not None:
        date = node.get("date")
        if date is None or str(date) < state.date_from:
            return False
    return True


def apply_graph_filter(state: GraphFilterState, graph: dict[str, Any]) -> dict[str, Any]:
    """Применить фильтр к ``GraphResponse`` целиком (§17.5).

    Apply the filter to a whole ``GraphResponse``. Оставляет узлы, проходящие
    :func:`node_matches`, затем отбрасывает рёбра, у которых любой из концов
    (``source``/``target``) был отфильтрован. Остальные ключи графа сохраняются.

    Keeps nodes passing :func:`node_matches`, then drops any edge whose
    ``source`` or ``target`` endpoint was filtered out. Other graph keys are
    preserved unchanged.
    """
    nodes: list[dict[str, Any]] = list(graph.get("nodes", []))
    edges: list[dict[str, Any]] = list(graph.get("edges", []))
    kept_nodes = [node for node in nodes if node_matches(state, node)]
    kept_ids = {node.get("id") for node in kept_nodes}
    kept_edges = [
        edge for edge in edges if edge.get("source") in kept_ids and edge.get("target") in kept_ids
    ]
    return {**graph, "nodes": kept_nodes, "edges": kept_edges}
