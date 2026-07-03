"""Graph-endpoint heavy-query truncation guard (§14.6).

Ограничивает размер ответа графовых эндпоинтов, чтобы тяжёлый запрос не выдал
неограниченный граф. Чистая детерминированная функция без сервера: сохраняем
первые ``max_nodes`` узлов во входном порядке, выкидываем рёбра, чьи
``source``/``target`` не попали в оставшийся набор, затем режем оставшиеся
рёбра до ``max_edges``. Флаг ``truncated`` поднимается, если что-то выброшено.

Caps the response size of graph endpoints so a heavy query cannot return an
unbounded graph. Pure and deterministic (no server):

* :class:`LimitResult` — frozen ``{nodes, edges, truncated, dropped_*}`` carrier
  with :meth:`as_dict`.
* :func:`apply_limits` — keep the first ``max_nodes`` nodes by input order,
  drop dangling edges, then cap remaining edges at ``max_edges``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LimitResult:
    """Неизменяемый результат усечения графа для ответа эндпоинта (§14.6).

    Frozen carrier for one truncation pass: the kept ``nodes`` and ``edges``
    (as tuples), the ``truncated`` flag, and how many ``dropped_nodes`` /
    ``dropped_edges`` were removed. :meth:`as_dict` gives a plain field view.
    """

    nodes: tuple[dict, ...]
    edges: tuple[dict, ...]
    truncated: bool
    dropped_nodes: int
    dropped_edges: int

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for JSON and assertions."""
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "truncated": self.truncated,
            "dropped_nodes": self.dropped_nodes,
            "dropped_edges": self.dropped_edges,
        }


def apply_limits(
    nodes: Sequence[dict],
    edges: Sequence[dict],
    *,
    max_nodes: int,
    max_edges: int,
) -> LimitResult:
    """Усечь граф до ``max_nodes`` узлов и ``max_edges`` рёбер (§14.6).

    Keeps the first ``max_nodes`` nodes by input order, drops every edge whose
    ``source`` or ``target`` is not in the kept node set, then caps the
    remaining edges at ``max_edges`` (also by input order). ``truncated`` is
    ``True`` whenever any node or edge was dropped; ``dropped_nodes`` /
    ``dropped_edges`` count the removals.
    """
    kept_nodes = tuple(nodes[:max_nodes])
    dropped_nodes = len(nodes) - len(kept_nodes)

    kept_ids = {node.get("id") for node in kept_nodes}
    # Only edges fully inside the kept node set survive the first pass.
    connected = [
        edge for edge in edges if edge.get("source") in kept_ids and edge.get("target") in kept_ids
    ]

    kept_edges = tuple(connected[:max_edges])
    # Dropped edges = dangling ones + those cut by the max_edges cap.
    dropped_edges = len(edges) - len(kept_edges)

    truncated = dropped_nodes > 0 or dropped_edges > 0
    return LimitResult(
        nodes=kept_nodes,
        edges=kept_edges,
        truncated=truncated,
        dropped_nodes=dropped_nodes,
        dropped_edges=dropped_edges,
    )
