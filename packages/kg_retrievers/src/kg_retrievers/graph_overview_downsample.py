"""§17.9 corpus-overview downsampler — свести большой граф к репрезентативному превью.

Режим «обзор корпуса» (§17.9) рисует граф целиком, но при тысячах узлов картинка
нечитаема и тяжела для UI. Этот модуль отличается от ``subgraph_extract`` (эго-/
индуцированный подграф по конкретному ``id``): здесь нет якорного узла — мы берём
**топ-K самых связных** узлов всего графа как представительный скелет.

- :func:`downsample_overview` — ранжирует узлы по степени (число инцидентных рёбер),
  ties → по ``evidenceCount`` desc, затем по ``id`` asc; оставляет top ``max_nodes``
  узлов и только те рёбра, у которых **оба** конца уцелели;
  ``dropped_count = total_nodes - kept_count``.
- :class:`OverviewGraph` — frozen-результат (``nodes``/``edges`` как ``tuple``,
  плюс ``kept_count``/``dropped_count``/``threshold``) с :meth:`~OverviewGraph.as_dict`
  для сериализации в camelCase.

Pure python — no numpy, no store/graph/DB access: на вход уже прочитанный граф-``dict``
вида ``{'nodes': [...], 'edges': [...]}``. Вход не мутируется.

Kuzu note: custom node props are NOT queryable columns — callers RETURN base columns and
read ``evidenceCount`` и прочее через ``get_node()`` перед сборкой узловых dict'ов сюда.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# §17.9 ключи полей во входном графе и в узловых/рёберных dict'ах.
NODES_KEY = "nodes"
EDGES_KEY = "edges"
ID_KEY = "id"
EVIDENCE_KEY = "evidenceCount"
SOURCE_KEY = "source"
TARGET_KEY = "target"


@dataclass(frozen=True)
class OverviewGraph:
    """Downsampled corpus-overview preview (§17.9).

    ``nodes``/``edges`` — уцелевшие узлы и рёбра (immutable ``tuple`` из dict'ов);
    ``kept_count`` — сколько узлов оставлено; ``dropped_count`` — сколько отброшено;
    ``threshold`` — использованный ``max_nodes`` (порог обрезки).
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    kept_count: int
    dropped_count: int
    threshold: int

    def as_dict(self) -> dict[str, Any]:
        """Serialize to camelCase for the UI/API layer (§17.9)."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "keptCount": self.kept_count,
            "droppedCount": self.dropped_count,
            "threshold": self.threshold,
        }


def _evidence_of(node: Mapping[str, Any]) -> float:
    """Read a node's ``evidenceCount``, defaulting to 0 if absent/non-numeric (§17.9)."""
    val = node.get(EVIDENCE_KEY, 0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _endpoints(edge: Mapping[str, Any]) -> tuple[Any, Any]:
    """Extract an edge's (source, target) node ids (§17.9)."""
    return edge.get(SOURCE_KEY), edge.get(TARGET_KEY)


def downsample_overview(graph: Mapping[str, Any], *, max_nodes: int = 500) -> OverviewGraph:
    """Reduce ``graph`` to its top-``max_nodes`` most-connected nodes (§17.9).

    Ранжирование узлов: степень (число инцидентных рёбер) desc → ``evidenceCount``
    desc → ``id`` asc. Оставляем top ``max_nodes`` узлов и только рёбра с обоими
    уцелевшими концами. ``dropped_count = total_nodes - kept_count``. Вход не мутируется.
    """
    nodes: Sequence[Mapping[str, Any]] = graph.get(NODES_KEY) or ()
    edges: Sequence[Mapping[str, Any]] = graph.get(EDGES_KEY) or ()
    total = len(nodes)

    # §17.9 степень каждого узла = число инцидентных рёбер (учитываем оба конца).
    degree: dict[Any, int] = {node.get(ID_KEY): 0 for node in nodes}
    for edge in edges:
        src, dst = _endpoints(edge)
        if src in degree:
            degree[src] += 1
        if dst in degree:
            degree[dst] += 1

    # §17.9 сортировка: степень desc, evidenceCount desc, id asc (стабильный ключ).
    ranked = sorted(
        nodes,
        key=lambda n: (-degree[n.get(ID_KEY)], -_evidence_of(n), _id_key(n.get(ID_KEY))),
    )
    kept_nodes = ranked[:max_nodes] if max_nodes >= 0 else []
    kept_ids = {n.get(ID_KEY) for n in kept_nodes}

    # §17.9 ребро выживает только если ОБА его конца уцелели.
    kept_edges = tuple(
        dict(e) for e in edges if _endpoints(e)[0] in kept_ids and _endpoints(e)[1] in kept_ids
    )

    kept_count = len(kept_nodes)
    return OverviewGraph(
        nodes=tuple(dict(n) for n in kept_nodes),
        edges=kept_edges,
        kept_count=kept_count,
        dropped_count=total - kept_count,
        threshold=max_nodes,
    )


def _id_key(node_id: Any) -> tuple[int, str]:
    """Total-order tie-break key on ``id`` (None sorts last, else string asc) (§17.9)."""
    return (1, "") if node_id is None else (0, str(node_id))
