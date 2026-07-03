"""GraphLegend visual-encoding builder for the §17.8 Graph Explorer (§5.2.3/§5.3).

Чистый билдер легенды (pure builder, no DB, no I/O): на вход — уже закодированный
§5.3 ``GraphResponse`` ``dict`` ({``nodes``, ``edges``}), произведённый
:mod:`kg_retrievers.graph_dto`; на выход — :class:`LegendSpec`, из которой фронтенд
рисует легенду Graph Explorer (§17.8). Легенда состоит из трёх частей: перечень
присутствующих типов узлов и рёбер (с их количеством и переключателем видимости) и
неизменного каталога визуальных каналов кодирования §5.2.3.

Visual-encoding (§5.2.3) — восемь каналов, описанных в :data:`ENCODING_RULES`:
``nodeColor``←type, ``nodeSize``←evidenceCount, ``hollowNode``←missingFields,
``lockIcon``←verified, ``edgeThickness``←evidenceCount, ``edgeOpacity``←confidence,
``dashedEdge``←inferred, ``redEdge``←contradicted.

Kuzu note: custom node props are NOT queryable columns — a retriever RETURNs base
columns and reads the rest via ``get_node``; by the time the ``GraphResponse`` reaches
this module every prop is already merged into the node/edge ``dict``, so nothing here
touches the store.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

# Каталог §5.2.3 визуальных каналов кодирования. Порядок и состав фиксированы: сперва
# четыре узловых канала, затем четыре рёберных. ``channel`` — имя канала на фронтенде,
# ``encodes`` — DTO-поле (§5.3), которое канал визуализирует, ``description_ru`` — RU.
ENCODING_RULES: tuple[dict[str, str], ...] = (
    {
        "channel": "nodeColor",
        "encodes": "type",
        "description_ru": "Цвет узла — тип сущности (Material, Paper, …).",
    },
    {
        "channel": "nodeSize",
        "encodes": "evidenceCount",
        "description_ru": "Размер узла — число подтверждающих доказательств.",
    },
    {
        "channel": "hollowNode",
        "encodes": "missingFields",
        "description_ru": "Полый узел — есть незаполненные обязательные поля.",
    },
    {
        "channel": "lockIcon",
        "encodes": "verified",
        "description_ru": "Иконка замка — узел верифицирован рецензентом.",
    },
    {
        "channel": "edgeThickness",
        "encodes": "evidenceCount",
        "description_ru": "Толщина ребра — число подтверждающих доказательств.",
    },
    {
        "channel": "edgeOpacity",
        "encodes": "confidence",
        "description_ru": "Прозрачность ребра — уверенность в связи.",
    },
    {
        "channel": "dashedEdge",
        "encodes": "inferred",
        "description_ru": "Пунктирное ребро — связь выведена, а не наблюдалась.",
    },
    {
        "channel": "redEdge",
        "encodes": "contradicted",
        "description_ru": "Красное ребро — связь противоречит другим (CONTRADICTS).",
    },
)


@dataclass(frozen=True)
class LegendSpec:
    """§17.8 GraphLegend — типы узлов/рёбер и каталог §5.2.3 каналов кодирования.

    ``node_types`` / ``edge_types`` — кортежи записей ``{type, count, visible}``,
    отсортированные по убыванию ``count``, затем по имени ``type`` (алфавит).
    ``encodings`` — неизменный каталог :data:`ENCODING_RULES` (всегда длины 8).
    """

    node_types: tuple[dict[str, Any], ...]
    edge_types: tuple[dict[str, Any], ...]
    encodings: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.3 camelCase legend payload (copies every entry)."""
        return {
            "nodeTypes": [dict(entry) for entry in self.node_types],
            "edgeTypes": [dict(entry) for entry in self.edge_types],
            "encodings": [dict(rule) for rule in self.encodings],
        }


def _edge_type(edge: dict[str, Any]) -> str:
    """RelType of an edge — ``type`` if present, else its display ``label`` (§5.3)."""
    value = edge.get("type") or edge.get("label")
    return str(value) if value else ""


def _type_entries(counts: Counter[str]) -> tuple[dict[str, Any], ...]:
    """Build sorted ``{type, count, visible}`` entries (desc count, then type asc)."""
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(
        {"type": type_name, "count": count, "visible": True} for type_name, count in ordered
    )


def build_legend(payload: dict[str, Any]) -> LegendSpec:
    """Derive the §17.8 :class:`LegendSpec` from an encoded §5.3 ``GraphResponse``.

    Counts distinct node ``type`` and edge ``type``/``label`` actually present in
    ``payload`` (a type absent from the payload never appears in the legend). Toggles
    (``visible``) default ``True``. The §5.2.3 :data:`ENCODING_RULES` catalogue is
    always attached in full, regardless of what the payload contains.
    """
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    node_counts: Counter[str] = Counter(str(node.get("type")) for node in nodes if node.get("type"))
    edge_counts: Counter[str] = Counter(et for edge in edges if (et := _edge_type(edge)))
    return LegendSpec(
        node_types=_type_entries(node_counts),
        edge_types=_type_entries(edge_counts),
        encodings=ENCODING_RULES,
    )
