"""Reagraph ``layoutType`` recommender from graph topology (§17.8 Graph Explorer).

Чистый рекомендатель (pure recommender, no DB, no I/O): по форме уже
материализованного графа (число узлов/рёбер + степень узлов) выбирает одну
раскладку Reagraph — ``forceDirected2d`` / ``radial`` / ``hierarchical`` /
``circular``. Дополняет :mod:`graph_render_mode`: тот выбирает *рендерер* и
перечисляет *допустимые* раскладки, но не выбирает конкретную из формы графа —
это делает данный модуль (§17.8).

Правила (в порядке приоритета):

1. Один доминирующий хаб (узел, инцидентный ≥60% рёбер) при заданных
   ``root_ids`` → ``radial`` (радиальная раскладка вокруг корня). Правило идёт
   первым: звезда с корнем — по сути дерево, но её лучше рисовать радиально.
2. Иначе дерево (``edge_count == node_count - 1`` и ``node_count >= 2``) →
   ``hierarchical`` (иерархическая раскладка для древовидных данных).
3. Иначе малый граф (``node_count <= 12``) → ``circular``.
4. Иначе → ``forceDirected2d`` (по умолчанию для больших/плотных графов).

Пустой граф (0 узлов) не считается малым и даёт ``forceDirected2d`` с
``is_tree=False``.

Kuzu note: custom node props are NOT queryable columns — a retriever RETURNs base
columns and reads the rest via ``get_node``; by the time a graph ``dict`` reaches
this module it already carries materialised ``nodes``/``edges``, so nothing here
touches the store.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Раскладки Reagraph, которыми оперирует рекомендатель (подмножество §17.8).
LAYOUT_HIERARCHICAL = "hierarchical"
LAYOUT_RADIAL = "radial"
LAYOUT_CIRCULAR = "circular"
LAYOUT_FORCE_2D = "forceDirected2d"

# Порог «малого» графа для circular и доля рёбер для доминирующего хаба (§17.8).
SMALL_GRAPH_MAX_NODES = 12
HUB_EDGE_FRACTION = 0.60

# Ключи-синонимы для id узла и концов ребра (совместимо с :mod:`graph_dto`).
_NODE_ID_KEYS: tuple[str, ...] = ("id", "identity", "key")
_EDGE_SOURCE_KEYS: tuple[str, ...] = ("source", "from", "src", "start")
_EDGE_TARGET_KEYS: tuple[str, ...] = ("target", "to", "dst", "end")


@dataclass(frozen=True)
class LayoutRecommendation:
    """§17.8 рекомендация раскладки Reagraph, выбранной из формы графа.

    - ``layout`` — одна из ``forceDirected2d`` / ``radial`` / ``hierarchical`` /
      ``circular``;
    - ``reason`` — RU/EN причина выбора (какое правило сработало);
    - ``node_count`` / ``edge_count`` — размеры входного графа, по которым
      принято решение;
    - ``is_tree`` — является ли граф деревом (``edge_count == node_count - 1`` и
      ``node_count >= 2``).
    """

    layout: str
    reason: str
    node_count: int
    edge_count: int
    is_tree: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.3 camelCase payload (``isTree`` is a plain bool)."""
        return {
            "layout": self.layout,
            "reason": self.reason,
            "nodeCount": self.node_count,
            "edgeCount": self.edge_count,
            "isTree": bool(self.is_tree),
        }


def _first_str(obj: dict[str, Any], keys: Sequence[str]) -> str | None:
    """First non-empty stringified value among ``keys`` in ``obj`` (else ``None``)."""
    for key in keys:
        val = obj.get(key)
        if val is not None and str(val) != "":
            return str(val)
    return None


def _edge_endpoints(edge: Any) -> tuple[str | None, str | None]:
    """Extract ``(source, target)`` ids from an edge ``dict`` (synonym-tolerant)."""
    if not isinstance(edge, dict):
        return None, None
    return _first_str(edge, _EDGE_SOURCE_KEYS), _first_str(edge, _EDGE_TARGET_KEYS)


def _incidence_counts(edges: Sequence[Any]) -> Counter[str]:
    """Count edges incident to each node id (each edge counts once per distinct end)."""
    counts: Counter[str] = Counter()
    for edge in edges:
        source, target = _edge_endpoints(edge)
        touched = {end for end in (source, target) if end is not None}
        for end in touched:
            counts[end] += 1
    return counts


def _has_dominant_hub(edges: Sequence[Any], edge_count: int) -> bool:
    """True when one node is incident to ≥ :data:`HUB_EDGE_FRACTION` of the edges."""
    if edge_count <= 0:
        return False
    counts = _incidence_counts(edges)
    if not counts:
        return False
    top = max(counts.values())
    return top >= HUB_EDGE_FRACTION * edge_count


def recommend_reagraph_layout(
    graph: dict[str, Any],
    *,
    root_ids: Sequence[str] | None = None,
) -> LayoutRecommendation:
    """Recommend a Reagraph ``layoutType`` from graph topology (§17.8).

    ``graph`` — материализованный граф вида ``{"nodes": [...], "edges": [...]}``;
    ``root_ids`` — опциональные корневые узлы (нужны для ``radial``). Возвращает
    :class:`LayoutRecommendation` по правилам приоритета, описанным в докстринге
    модуля. Не обращается к хранилищу (pure).
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_count = len(nodes)
    edge_count = len(edges)

    is_tree = node_count >= 2 and edge_count == node_count - 1

    # A star with an explicit root is best rendered radially even though it is
    # topologically a tree — the hub+root_ids rule therefore takes priority over the
    # generic tree→hierarchical rule (§17.8).
    if root_ids and _has_dominant_hub(edges, edge_count):
        layout = LAYOUT_RADIAL
        reason = (
            f"radial: single dominant hub incident to >= {int(HUB_EDGE_FRACTION * 100)}% "
            f"of {edge_count} edges with root_ids given (§17.8)"
        )
    elif is_tree:
        layout = LAYOUT_HIERARCHICAL
        reason = (
            f"hierarchical: tree shape (edges {edge_count} == nodes {node_count} - 1), "
            "hierarchical layout for tree-like data (§17.8)"
        )
    elif 1 <= node_count <= SMALL_GRAPH_MAX_NODES:
        layout = LAYOUT_CIRCULAR
        reason = (
            f"circular: small graph (nodes {node_count} <= {SMALL_GRAPH_MAX_NODES}), "
            "non-tree without radial hub (§17.8)"
        )
    else:
        layout = LAYOUT_FORCE_2D
        reason = (
            f"forceDirected2d: default for large/dense/empty graph "
            f"(nodes {node_count}, edges {edge_count}) (§17.8)"
        )

    return LayoutRecommendation(
        layout=layout,
        reason=reason,
        node_count=node_count,
        edge_count=edge_count,
        is_tree=is_tree,
    )
