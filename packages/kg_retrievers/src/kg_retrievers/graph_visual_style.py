"""GraphEncoding single-source-of-truth resolver (§17.5 / §5.2.3 visual encodings).

Чистый резолвер (pure, no DB, no I/O): превращает *поля* кодирования, которые
эмитит :mod:`kg_retrievers.graph_dto` (§5.3 ``GraphNode`` / ``GraphEdge``), в
конкретные *значения* рендера. Это Python-зеркало фронтового ``graphEncoding.ts`` —
единый источник правды для палитры цветов, размеров, толщины, прозрачности и стилей
(hollow / locked / dashed / red). Никакой другой палитры в репозитории нет.

Visual-encoding (§5.2.3), восемь каналов:
    ``nodeColor``     ← ``type``            (см. :data:`TYPE_COLORS`)
    ``nodeSize``      ← ``evidenceCount``   (:data:`MIN_SIZE` + :data:`SIZE_K`·√n)
    ``hollowNode``    ← ``missingFields``   (непусто → hollow)
    ``lockIcon``      ← ``verified``        (True → locked)
    ``edgeThickness`` ← ``evidenceCount``   (:data:`MIN_WIDTH` + :data:`WIDTH_K`·√n)
    ``edgeOpacity``   ← ``confidence``      (clamp в [:data:`MIN_OPACITY`, 1.0])
    ``dashedEdge``    ← ``inferred``        (True → dashed)
    ``redEdge``       ← ``contradicted``    (True → :data:`RED`)

Kuzu note: custom node props are NOT queryable columns — ретривер RETURN'ит базовые
колонки и читает остальное через ``get_node``; к этому модулю узел/ребро приходит уже
как обычный ``dict`` со слитыми полями, поэтому здесь стор не трогается.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# -- palette / constants (§5.2.3) --------------------------------------------------

# Цвет по умолчанию для неизвестного / отсутствующего типа узла (нейтральный серый).
DEFAULT_COLOR = "#9e9e9e"
# Красный для противоречащих рёбер (§8.2 CONTRADICTS → red edge, §5.2.3).
RED = "#d32f2f"
# Нейтральный цвет обычного ребра (не противоречащего).
EDGE_COLOR = "#8a8a8a"

# Размер узла: MIN_SIZE + SIZE_K·√evidenceCount (монотонно растёт по числу свидетельств).
MIN_SIZE = 4.0
SIZE_K = 2.0

# Толщина ребра: MIN_WIDTH + WIDTH_K·√evidenceCount.
MIN_WIDTH = 1.0
WIDTH_K = 0.75

# Прозрачность ребра: clamp(confidence) в [MIN_OPACITY, MAX_OPACITY]; None → DEFAULT.
MIN_OPACITY = 0.15
MAX_OPACITY = 1.0
DEFAULT_OPACITY = 0.6

# Палитра цветов по типу узла (§5.3 NodeLabel → hex). Единственная палитра в репо:
# фронтовый ``graphEncoding.ts`` зеркалит ровно эти значения. Ключ — строка типа из
# §5.3 payload (см. :class:`kg_schema.labels.NodeLabel`); неизвестный тип → DEFAULT_COLOR.
TYPE_COLORS: dict[str, str] = {
    # -- document structure --
    "Document": "#607d8b",
    "Paper": "#3f51b5",
    "Section": "#78909c",
    "Paragraph": "#90a4ae",
    "Table": "#546e7a",
    "Figure": "#455a64",
    "Chunk": "#b0bec5",
    # -- knowledge / provenance --
    "Evidence": "#8d6e63",
    "Claim": "#7e57c2",
    "Finding": "#5e35b1",
    # -- experiment --
    "Experiment": "#ff7043",
    "Sample": "#ffa726",
    # -- materials --
    "Material": "#43a047",
    "Alloy": "#66bb6a",
    "ChemicalElement": "#26a69a",
    "Composition": "#009688",
    # -- process --
    "ProcessingRegime": "#fb8c00",
    "ProcessingStep": "#ffb300",
    "Parameter": "#fdd835",
    # -- equipment / people --
    "Equipment": "#8e24aa",
    "Lab": "#ab47bc",
    "ResearchTeam": "#ce93d8",
    "Person": "#ec407a",
    # -- measurement --
    "Property": "#1e88e5",
    "Measurement": "#039be5",
    "Unit": "#4fc3f7",
    "Method": "#00acc1",
    "Dataset": "#26c6da",
    "Project": "#5c6bc0",
    # -- curation / gaps --
    "Decision": "#9ccc65",
    "CurationEvent": "#c0ca33",
    "Gap": "#e53935",
    "Contradiction": "#c62828",
    # -- domain: mining-metallurgy (§24.2) --
    "Geography": "#6d4c41",
    "Country": "#795548",
    "Facility": "#a1887f",
    "TechnologySolution": "#00897b",
    "Recommendation": "#7cb342",
    "Limitation": "#f4511e",
    "ApplicabilityCondition": "#d81b60",
    "TechnologyComparison": "#5e35b1",
    "KnowledgeClaim": "#673ab7",
    "Standard": "#3949ab",
    "TechnoEconomicIndicator": "#00838f",
}


# -- style value objects -----------------------------------------------------------


@dataclass(frozen=True)
class NodeStyle:
    """Конкретные render-значения узла (§5.2.3): цвет, размер, hollow, locked."""

    color: str
    size: float
    hollow: bool
    locked: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready ``dict`` (frontend graphEncoding node style)."""
        return {
            "color": self.color,
            "size": self.size,
            "hollow": self.hollow,
            "locked": self.locked,
        }


@dataclass(frozen=True)
class EdgeStyle:
    """Конкретные render-значения ребра (§5.2.3): цвет, толщина, прозрачность, dashed."""

    color: str
    width: float
    opacity: float
    dashed: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready ``dict`` (frontend graphEncoding edge style)."""
        return {
            "color": self.color,
            "width": self.width,
            "opacity": self.opacity,
            "dashed": self.dashed,
        }


# -- helpers -----------------------------------------------------------------------


def _lookup(item: dict[str, Any], *keys: str) -> Any:
    """First present, non-``None`` value among ``keys`` (camelCase or snake_case)."""
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _evidence_count(item: dict[str, Any]) -> int:
    """Non-negative ``evidenceCount`` (camel/snake); missing / invalid / <0 → 0."""
    raw = _lookup(item, "evidenceCount", "evidence_count")
    try:
        count = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def _size_for(count: int) -> float:
    """Node size / edge base metric: :data:`MIN_SIZE` + :data:`SIZE_K`·√count."""
    return MIN_SIZE + SIZE_K * math.sqrt(count)


def _width_for(count: int) -> float:
    """Edge width: :data:`MIN_WIDTH` + :data:`WIDTH_K`·√count."""
    return MIN_WIDTH + WIDTH_K * math.sqrt(count)


def _opacity_for(confidence: Any) -> float:
    """Clamp ``confidence`` into [:data:`MIN_OPACITY`, 1.0]; ``None`` → :data:`DEFAULT_OPACITY`."""
    if confidence is None:
        return DEFAULT_OPACITY
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return DEFAULT_OPACITY
    return max(MIN_OPACITY, min(MAX_OPACITY, value))


# -- resolvers ---------------------------------------------------------------------


def node_style(node: dict[str, Any]) -> NodeStyle:
    """Resolve §5.2.3 node encoding fields to a concrete :class:`NodeStyle`.

    ``type`` → color (:data:`TYPE_COLORS`, unknown/None → :data:`DEFAULT_COLOR`);
    ``evidenceCount`` → size (:func:`_size_for`); non-empty ``missingFields`` → hollow;
    truthy ``verified`` → locked. Accepts both camelCase (DTO output) and snake_case.
    """
    node_type = _lookup(node, "type", "label")
    color = TYPE_COLORS.get(str(node_type), DEFAULT_COLOR) if node_type else DEFAULT_COLOR
    size = _size_for(_evidence_count(node))
    missing = _lookup(node, "missingFields", "missing_fields")
    hollow = bool(missing)
    locked = bool(_lookup(node, "verified"))
    return NodeStyle(color=color, size=size, hollow=hollow, locked=locked)


def edge_style(edge: dict[str, Any]) -> EdgeStyle:
    """Resolve §5.2.3 edge encoding fields to a concrete :class:`EdgeStyle`.

    ``contradicted`` → color :data:`RED` (else :data:`EDGE_COLOR`); ``evidenceCount`` →
    width (:func:`_width_for`); ``confidence`` → opacity (clamped, :func:`_opacity_for`);
    truthy ``inferred`` → dashed. Accepts both camelCase (DTO output) and snake_case.
    """
    contradicted = bool(_lookup(edge, "contradicted"))
    color = RED if contradicted else EDGE_COLOR
    width = _width_for(_evidence_count(edge))
    opacity = _opacity_for(_lookup(edge, "confidence"))
    dashed = bool(_lookup(edge, "inferred"))
    return EdgeStyle(color=color, width=width, opacity=opacity, dashed=dashed)


def style_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a §5.3 ``GraphResponse`` with a ``style`` key on every node/edge.

    Originals are never mutated: each node/edge is shallow-copied and gains a ``style``
    ``dict`` (:meth:`NodeStyle.as_dict` / :meth:`EdgeStyle.as_dict`). Missing/empty
    ``nodes``/``edges`` yield empty lists; other top-level keys are carried through.
    """
    out: dict[str, Any] = dict(graph)
    styled_nodes: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        copied = dict(node)
        copied["style"] = node_style(node).as_dict()
        styled_nodes.append(copied)
    styled_edges: list[dict[str, Any]] = []
    for edge in graph.get("edges") or []:
        copied = dict(edge)
        copied["style"] = edge_style(edge).as_dict()
        styled_edges.append(copied)
    out["nodes"] = styled_nodes
    out["edges"] = styled_edges
    return out
