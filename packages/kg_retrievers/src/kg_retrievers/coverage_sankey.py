"""Gap-dashboard coverage sankey builder (§17.14 / §5.2.7).

Строит ECharts ``sankey`` payload (полезную нагрузку) для дашборда пробелов покрытия:
три колонки узлов Material -> ProcessingRegime -> Property (материал -> режим
обработки -> свойство), где ширина связи (link width) равна числу свидетельств /
экспериментов (evidence / experiment count).

Pure, offline, deterministic builder — no store, no clock, no LLM. Вход — список словарей
``{material, regime, property, count}`` (coverage triples, тройки покрытия). Node names
are column-prefixed (``M:``/``R:``/``P:``) so identical labels in different columns never
collide, and links summing identical ``(source, target)`` pairs aggregate their counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Column prefixes (§5.2.7): keep material/regime/property namespaces disjoint (RU: колонки).
_MATERIAL_PREFIX = "M:"
_REGIME_PREFIX = "R:"
_PROPERTY_PREFIX = "P:"

# Node depth per column (§5.2.7): 0 material, 1 regime, 2 property.
_DEPTH_MATERIAL = 0
_DEPTH_REGIME = 1
_DEPTH_PROPERTY = 2


@dataclass(frozen=True)
class SankeyPayload:
    """Immutable ECharts ``sankey`` payload (§5.2.7).

    ``nodes`` — кортеж узлов ``{name, depth}``; ``links`` — кортеж связей
    ``{source, target, value}`` (source/target ссылаются на ``name`` узлов).
    """

    nodes: tuple[dict[str, Any], ...]
    links: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Return a JSON-serialisable ``{nodes, links}`` mapping (§5.2.7)."""
        return {
            "nodes": [dict(node) for node in self.nodes],
            "links": [dict(link) for link in self.links],
        }


def build_coverage_sankey(triples: list[dict]) -> SankeyPayload:
    """Build a coverage sankey payload from coverage triples (§17.14 / §5.2.7).

    Each triple is ``{material, regime, property, count}``. Nodes are emitted in
    first-seen order per column, prefixed by column (``M:``/``R:``/``P:``). Two links per
    triple — material->regime and regime->property — with identical ``(source, target)``
    pairs aggregating their ``count`` (RU: суммирование весов связей).
    """
    node_depths: dict[str, int] = {}
    node_order: list[str] = []
    link_values: dict[tuple[str, str], int] = {}
    link_order: list[tuple[str, str]] = []

    def _register(name: str, depth: int) -> None:
        if name not in node_depths:
            node_depths[name] = depth
            node_order.append(name)

    def _add_link(source: str, target: str, value: int) -> None:
        key = (source, target)
        if key not in link_values:
            link_values[key] = 0
            link_order.append(key)
        link_values[key] += value

    for triple in triples:
        material = _MATERIAL_PREFIX + str(triple["material"])
        regime = _REGIME_PREFIX + str(triple["regime"])
        prop = _PROPERTY_PREFIX + str(triple["property"])
        count = int(triple["count"])

        _register(material, _DEPTH_MATERIAL)
        _register(regime, _DEPTH_REGIME)
        _register(prop, _DEPTH_PROPERTY)

        _add_link(material, regime, count)
        _add_link(regime, prop, count)

    nodes = tuple({"name": name, "depth": node_depths[name]} for name in node_order)
    links = tuple(
        {"source": source, "target": target, "value": link_values[(source, target)]}
        for source, target in link_order
    )
    return SankeyPayload(nodes=nodes, links=links)


__all__ = ["SankeyPayload", "build_coverage_sankey"]
