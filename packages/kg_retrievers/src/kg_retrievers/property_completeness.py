"""§3.18/§8 — per-label required-property fill-rate matrix over a whole store.

Матрица заполненности обязательных свойств (*required-property fill-rate matrix*):
агрегирует по всему графу, насколько плотно заполнены обязательные доменные свойства
каждой метки (§3.18/§8). Для каждой метки считается доля узлов, у которых данное
обязательное свойство присутствует (``fill_rate``), и абсолютное число узлов, где оно
отсутствует (``missing_counts``).

Алгоритм (§3.18): узлы перечисляются запросом ``MATCH (n:Node) RETURN n.id, n.label``
(в Kuzu кастомные свойства НЕ являются запрашиваемыми колонками, поэтому в ``RETURN`` идут
только базовые ``id``/``label``); полный словарь свойств каждого узла читается через
:meth:`KuzuGraphStore.get_node`, который разворачивает JSON ``props``. Обязательные свойства
берутся из :func:`kg_schema.node_validation.required_props`, а факт их отсутствия — из
:func:`kg_schema.node_validation.missing_fields` (единый источник правды по меткам).

Метка без объявленных обязательных свойств (например ``Material``) имеет пустой
``required``/``fill_rate`` и считается «полной» (:attr:`LabelCompleteness.complete` = ``True``):
предъявлять к ней нечего. Модуль ничего не пишет в граф — это чистое чтение/агрегация.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kg_schema.node_validation import missing_fields, required_props

if TYPE_CHECKING:
    from kg_retrievers.graph_store import KuzuGraphStore


@dataclass(frozen=True)
class LabelCompleteness:
    """Required-property fill rates for all nodes of one label (§3.18/§8).

    Attributes
    ----------
    label:
        The node label these figures describe.
    n_nodes:
        Number of nodes observed with :attr:`label`.
    required:
        The required-property names declared for :attr:`label` (order per catalog).
    fill_rate:
        ``prop → fraction of nodes (0.0..1.0) that carry the property``. Empty when
        the label declares no required properties.
    missing_counts:
        ``prop → number of nodes missing the property`` (only props with >0 misses).
    """

    label: str
    n_nodes: int
    required: tuple[str, ...]
    fill_rate: dict[str, float]
    missing_counts: dict[str, int]

    @property
    def complete(self) -> bool:
        """``True`` iff every required property is present on every node (§3.18).

        A label with no required properties is vacuously complete.
        """
        return all(rate == 1.0 for rate in self.fill_rate.values())

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.18)."""
        return {
            "label": self.label,
            "n_nodes": self.n_nodes,
            "required": list(self.required),
            "fill_rate": dict(self.fill_rate),
            "missing_counts": dict(self.missing_counts),
            "complete": self.complete,
        }


@dataclass(frozen=True)
class CompletenessMatrix:
    """Store-wide required-property completeness, one row per label (§3.18/§8)."""

    by_label: dict[str, LabelCompleteness]
    total_nodes: int

    @property
    def overall_complete(self) -> bool:
        """``True`` iff every observed label is itself complete (§3.18)."""
        return all(lc.complete for lc in self.by_label.values())

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict keyed by label (§3.18)."""
        return {
            "total_nodes": self.total_nodes,
            "overall_complete": self.overall_complete,
            "by_label": {label: lc.as_dict() for label, lc in self.by_label.items()},
        }


def property_completeness(store: KuzuGraphStore) -> CompletenessMatrix:
    """Aggregate required-property fill rates per label across ``store`` (§3.18/§8).

    Enumerates ``(id, label)`` for all nodes, loads each node via
    :meth:`KuzuGraphStore.get_node` (merging the JSON ``props``), and tallies for every
    required property how many nodes carry it. Returns a :class:`CompletenessMatrix`.
    """
    # prop-presence tallies per label, plus node counts.
    counts: dict[str, int] = {}
    missing: dict[str, dict[str, int]] = {}
    total = 0
    for node_id, label in store.rows("MATCH (n:Node) RETURN n.id, n.label"):
        total += 1
        label = str(label)
        counts[label] = counts.get(label, 0) + 1
        missing.setdefault(label, {})
        node = store.get_node(node_id)
        if node is None:
            continue
        for name in missing_fields(node):
            missing[label][name] = missing[label].get(name, 0) + 1

    by_label: dict[str, LabelCompleteness] = {}
    for label, n_nodes in counts.items():
        required = required_props(label)
        miss = missing[label]
        fill_rate = {name: (n_nodes - miss.get(name, 0)) / n_nodes for name in required}
        missing_counts = {name: c for name, c in miss.items() if c > 0}
        by_label[label] = LabelCompleteness(
            label=label,
            n_nodes=n_nodes,
            required=required,
            fill_rate=fill_rate,
            missing_counts=missing_counts,
        )
    return CompletenessMatrix(by_label=by_label, total_nodes=total)


__all__ = [
    "CompletenessMatrix",
    "LabelCompleteness",
    "property_completeness",
]
