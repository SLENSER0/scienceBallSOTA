"""Path-search result highlighter for the §17.8 ``POST /graph/path`` feature (§5.3).

Чистый аннотатор (pure annotator, no DB, no I/O): на вход — уже закодированный
§5.3 ``GraphResponse`` ``dict`` ({``nodes``, ``edges``}) и упорядоченный список id
узлов найденного пути (*found path*); на выход — копия ``GraphResponse``, где узлы и
рёбра пути помечены визуальным флагом ``onPath`` для Graph Explorer (§17.8). В отличие
от :mod:`kg_retrievers.path_ranking` (который лишь *оценивает* пути), этот модуль
*наносит* уже выбранный путь на граф.

English: :func:`highlight_path` returns a copy of the ``GraphResponse`` where every
node on the path gets ``onPath=True`` plus a zero-based ``pathOrder`` (its position in
``path_node_ids``), every off-path node gets ``onPath=False``, and every edge joining a
consecutive pair of path nodes gets ``onPath=True`` (all other edges ``onPath=False``).
A consecutive pair ``(n_i, n_{i+1})`` is *connected* if some edge matches either
``(source, target)`` or ``(target, source)`` — stored direction is ignored.
:func:`path_highlight_summary` returns a frozen :class:`PathHighlight` describing the
same path: the node ids, the connecting edge ids (in path order), the index tuples of
pairs with **no** connecting edge (``missing_segments``) and the edge ``length``
(``len(path) - 1``, floored at 0).

Kuzu note: custom node props are NOT queryable columns — a retriever RETURNs base
columns and reads the rest via ``get_node``; by the time the ``GraphResponse`` reaches
this module every prop is already merged into the node/edge ``dict``, so nothing here
touches the store.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PathHighlight:
    """§17.8 path-highlight summary — узлы, рёбра и разрывы найденного пути.

    ``node_ids`` — упорядоченный кортеж id узлов пути; ``edge_ids`` — id соединяющих
    рёбер в порядке пути (только для реально соединённых пар); ``missing_segments`` —
    кортеж индексных пар ``(i, i+1)`` для пар без соединяющего ребра; ``length`` —
    число рёбер пути (``len(node_ids) - 1``, но не меньше 0).
    """

    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    missing_segments: tuple[tuple[int, int], ...]
    length: int

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{nodeIds, edgeIds, missingSegments, length}`` (lists, camelCase)."""
        return {
            "nodeIds": list(self.node_ids),
            "edgeIds": list(self.edge_ids),
            "missingSegments": [list(pair) for pair in self.missing_segments],
            "length": self.length,
        }


def _endpoints(edge: dict[str, Any]) -> tuple[str, str]:
    """The ``(source, target)`` id pair of an edge (§5.3), coerced to ``str``."""
    return str(edge.get("source", "")), str(edge.get("target", ""))


def _edge_id(edge: dict[str, Any]) -> str:
    """The edge id (§5.3 ``id``), coerced to ``str`` (empty when absent)."""
    return str(edge.get("id", ""))


def _connecting_edge(edge: dict[str, Any], a: str, b: str) -> bool:
    """True if ``edge`` joins ids ``a`` and ``b`` in either stored direction (§17.8)."""
    source, target = _endpoints(edge)
    return (source == a and target == b) or (source == b and target == a)


def _path_order(path_node_ids: Sequence[str]) -> dict[str, int]:
    """Map each path node id to its **first** zero-based position in the path."""
    order: dict[str, int] = {}
    for index, node_id in enumerate(path_node_ids):
        key = str(node_id)
        if key not in order:
            order[key] = index
    return order


def highlight_path(graph: dict[str, Any], path_node_ids: Sequence[str]) -> dict[str, Any]:
    """Annotate a §5.3 ``GraphResponse`` copy with the found §17.8 path (§17.8).

    Returns a **new** ``dict`` (the input is never mutated): every node whose id is on
    the path gets ``onPath=True`` and ``pathOrder`` equal to its zero-based index in
    ``path_node_ids``; every other node gets ``onPath=False`` (no ``pathOrder``). An
    edge joining a consecutive path pair — matching ``(source, target)`` or
    ``(target, source)`` — gets ``onPath=True``; all other edges ``onPath=False``.
    """
    order = _path_order(path_node_ids)
    pairs = _consecutive_pairs(path_node_ids)

    nodes_out: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        marked = dict(node)
        node_id = str(node.get("id", ""))
        if node_id in order:
            marked["onPath"] = True
            marked["pathOrder"] = order[node_id]
        else:
            marked["onPath"] = False
        nodes_out.append(marked)

    edges_out: list[dict[str, Any]] = []
    for edge in graph.get("edges") or []:
        marked = dict(edge)
        marked["onPath"] = any(_connecting_edge(edge, a, b) for a, b in pairs)
        edges_out.append(marked)

    result = dict(graph)
    result["nodes"] = nodes_out
    result["edges"] = edges_out
    return result


def _consecutive_pairs(path_node_ids: Sequence[str]) -> list[tuple[str, str]]:
    """Adjacent id pairs ``(n_i, n_{i+1})`` of the path, coerced to ``str``."""
    ids = [str(node_id) for node_id in path_node_ids]
    return [(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]


def path_highlight_summary(graph: dict[str, Any], path_node_ids: Sequence[str]) -> PathHighlight:
    """Summarise the §17.8 found path over a §5.3 ``GraphResponse`` (§17.8).

    Walks each consecutive pair ``(n_i, n_{i+1})``: the first edge joining it in either
    stored direction contributes its id to ``edge_ids`` (in path order); a pair with no
    such edge contributes its ``(i, i+1)`` index tuple to ``missing_segments``. ``length``
    is ``len(path_node_ids) - 1`` (floored at 0), so a single-node path yields ``0`` and
    no ``edge_ids``. The input graph is only read, never mutated.
    """
    ids = tuple(str(node_id) for node_id in path_node_ids)
    edges = graph.get("edges") or []

    edge_ids: list[str] = []
    missing_segments: list[tuple[int, int]] = []
    for index, (a, b) in enumerate(_consecutive_pairs(ids)):
        match = next((edge for edge in edges if _connecting_edge(edge, a, b)), None)
        if match is None:
            missing_segments.append((index, index + 1))
        else:
            edge_ids.append(_edge_id(match))

    return PathHighlight(
        node_ids=ids,
        edge_ids=tuple(edge_ids),
        missing_segments=tuple(missing_segments),
        length=max(0, len(ids) - 1),
    )
