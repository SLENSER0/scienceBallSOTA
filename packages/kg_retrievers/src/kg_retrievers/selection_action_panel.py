"""View-model for the lasso/box-selection action panel over a subgraph (§17.8).

Экран Graph Explorer позволяет обвести лассо/рамкой набор узлов; над выделением
показывается панель действий со сводкой. ``subgraph_extract`` строит сам подграф,
но не формирует эту сводку — здесь мы её и собираем: сколько узлов/рёбер попало в
выделение, разбивка по типам, средняя уверенность и список предлагаемых действий.

Отличие от ``graph_selection_action.select_subgraph``: тот возвращает сами
элементы подграфа плюс ``ask_context`` для агента; здесь же чистая *view-model*
панели — счётчики, агрегаты и офферы кнопок, без переноса самих узлов/рёбер.

Contract (§5.3 payload shapes):
  * ``graph["nodes"]`` — dicts с как минимум ``id``; опциональные ``type`` и
    числовой ``confidence`` участвуют в агрегатах;
  * ``graph["edges"]`` — dicts с ``source``/``target`` по ``id`` узлов.

Ребро индуцировано только если ОБА эндпоинта выделены (внешние рёбра, у которых
один конец вне выделения, не считаются). Действие ``resolve_gaps`` добавляется
только когда в выделении есть узел типа ``Gap``. Deterministic, no I/O, no clock.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_BASE_ACTIONS: tuple[str, ...] = ("export_subgraph", "ask_agent")
_GAP_ACTION: str = "resolve_gaps"
_GAP_TYPE: str = "Gap"


@dataclass(frozen=True)
class SelectionPanel:
    """Summary view-model of a lasso/box selection's action panel (§17.8).

    ``node_ids`` — отсортированные id выделенных узлов, присутствующих в графе;
    ``type_counts`` — разбивка выделения по ``type``; ``avg_confidence`` — средняя
    уверенность выделенных узлов (0.0, если выделение пусто); ``actions`` — офферы
    кнопок панели.
    """

    node_ids: tuple[str, ...]
    node_count: int
    edge_count: int
    type_counts: dict[str, int]
    avg_confidence: float
    has_gap: bool
    actions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialize to the frontend JSON shape (camelCase per §5.3)."""
        return {
            "nodeIds": list(self.node_ids),
            "nodeCount": self.node_count,
            "edgeCount": self.edge_count,
            "typeCounts": dict(self.type_counts),
            "avgConfidence": self.avg_confidence,
            "hasGap": self.has_gap,
            "actions": list(self.actions),
        }


def build_selection_panel(
    graph: dict[str, Any],
    selected_ids: Iterable[str],
) -> SelectionPanel:
    """Build the §17.8 selection action panel from a §5.3 GraphResponse dict.

    ``node_ids`` — выделение, пересечённое с реальными узлами графа (отсортировано;
    несуществующие id отбрасываются). ``edge_count`` считает только индуцированные
    рёбра, у которых оба конца выделены. ``type_counts`` группирует выделенные узлы
    по ``type``; ``avg_confidence`` — среднее их ``confidence`` (0.0 при пустом
    выделении). ``has_gap`` истинно при наличии узла типа ``Gap``, и тогда к базовым
    действиям добавляется ``resolve_gaps``.
    """
    selection: set[str] = set(selected_ids)
    raw_nodes: list[dict[str, Any]] = list(graph.get("nodes") or [])
    raw_edges: list[dict[str, Any]] = list(graph.get("edges") or [])

    kept: list[dict[str, Any]] = [n for n in raw_nodes if n.get("id") in selection]
    present: set[str] = {n.get("id") for n in kept}

    node_ids: tuple[str, ...] = tuple(sorted(present))
    edge_count: int = sum(
        1 for e in raw_edges if e.get("source") in present and e.get("target") in present
    )
    type_counts: dict[str, int] = dict(Counter(n.get("type") for n in kept))
    has_gap: bool = any(n.get("type") == _GAP_TYPE for n in kept)

    confidences: list[float] = [
        float(n["confidence"]) for n in kept if n.get("confidence") is not None
    ]
    avg_confidence: float = sum(confidences) / len(confidences) if confidences else 0.0

    actions: tuple[str, ...] = _BASE_ACTIONS + ((_GAP_ACTION,) if has_gap else ())

    return SelectionPanel(
        node_ids=node_ids,
        node_count=len(node_ids),
        edge_count=edge_count,
        type_counts=type_counts,
        avg_confidence=avg_confidence,
        has_gap=has_gap,
        actions=actions,
    )
