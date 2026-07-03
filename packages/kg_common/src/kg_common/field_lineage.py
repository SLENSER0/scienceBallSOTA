"""Field/column-level lineage — прослеживаемость на уровне полей (§10.5).

While table-level lineage records that a *dataset* feeds a *node label*, §10.5
asks for the finer «column/field-level lineage: extraction schema fields ->
node properties». This module maps individual **extraction-schema fields** to
the concrete **Neo4j node properties** they populate, optionally noting the
*transform* applied on the way (identity, normalization, …).

A :class:`FieldEdge` is a single directed hop «from_field -> (label, property)»
carrying a ``transform`` label. A :class:`FieldLineage` is the immutable bag of
such edges, with lookups both ways:

* :meth:`FieldLineage.upstream_of` — which fields feed a given node property?
* :meth:`FieldLineage.downstream_of` — which properties does a field populate?

Everything is pure and side-effect free: no I/O, no wall-clock, no globals.
Edges are frozen dataclasses, so callers cannot mutate an edge after
construction. Duplicate ``(field, label, property)`` triples collapse to a
single edge («дедупликация рёбер»).

Public API:

* :class:`FieldEdge`   — frozen ``{from_field, to_label, to_property,
  transform}`` record with :meth:`~FieldEdge.as_dict`.
* :class:`FieldLineage` — frozen tuple of edges with :meth:`~FieldLineage.as_dict`,
  :meth:`~FieldLineage.upstream_of`, :meth:`~FieldLineage.downstream_of`.
* :func:`build_field_lineage` — build a lineage from a field->target mapping.
* :func:`coverage` — fraction of schema fields with at least one edge.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

__all__ = [
    "FieldEdge",
    "FieldLineage",
    "build_field_lineage",
    "coverage",
]


# --------------------------------------------------------------------------- #
# FieldEdge — одно ребро прослеживаемости                                     #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FieldEdge:
    """One field->property hop — одно ребро «поле -> свойство узла» (§10.5).

    ``from_field`` names an extraction-schema field; ``to_label`` / ``to_property``
    name the Neo4j node label and property it populates; ``transform`` labels the
    mapping applied (defaults to ``"identity"`` — тождественное отображение).
    """

    from_field: str
    to_label: str
    to_property: str
    transform: str = "identity"

    def as_dict(self) -> dict[str, str]:
        """Return a plain ``dict`` view — словарное представление ребра."""
        return {
            "from_field": self.from_field,
            "to_label": self.to_label,
            "to_property": self.to_property,
            "transform": self.transform,
        }


# --------------------------------------------------------------------------- #
# FieldLineage — граф прослеживаемости полей                                  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FieldLineage:
    """Immutable bag of field edges — неизменяемый набор рёбер полей (§10.5)."""

    edges: tuple[FieldEdge, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        """Return a nested ``dict`` view — вложенное словарное представление."""
        return {"edges": [edge.as_dict() for edge in self.edges]}

    def upstream_of(self, label: str, prop: str) -> tuple[str, ...]:
        """Fields feeding node property ``label.prop`` — исходные поля.

        Returns an empty tuple for an unknown property («неизвестное свойство»).
        Order follows first appearance in :attr:`edges`; duplicates are removed.
        """
        out: list[str] = []
        for edge in self.edges:
            if edge.to_label == label and edge.to_property == prop and edge.from_field not in out:
                out.append(edge.from_field)
        return tuple(out)

    def downstream_of(self, from_field: str) -> tuple[tuple[str, str], ...]:
        """Node properties populated by ``from_field`` — целевые свойства.

        Each item is a ``(label, property)`` pair. Returns an empty tuple for an
        unknown field. Order follows first appearance; duplicates are removed.
        """
        out: list[tuple[str, str]] = []
        for edge in self.edges:
            if edge.from_field == from_field:
                pair = (edge.to_label, edge.to_property)
                if pair not in out:
                    out.append(pair)
        return tuple(out)


# --------------------------------------------------------------------------- #
# Builders — построители                                                      #
# --------------------------------------------------------------------------- #


def build_field_lineage(mapping: Mapping[str, tuple[str, str, str]]) -> FieldLineage:
    """Build a :class:`FieldLineage` from a field->target mapping (§10.5).

    Each mapping value is a ``(label, property, transform)`` triple. Duplicate
    ``(field, label, property)`` triples collapse to a single edge, keeping the
    first-seen transform («дедупликация по ключу поле+метка+свойство»).
    """
    edges: list[FieldEdge] = []
    seen: set[tuple[str, str, str]] = set()
    for from_field, (label, prop, transform) in mapping.items():
        key = (from_field, label, prop)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            FieldEdge(
                from_field=from_field,
                to_label=label,
                to_property=prop,
                transform=transform,
            )
        )
    return FieldLineage(edges=tuple(edges))


def coverage(lineage: FieldLineage, schema_fields: Iterable[str]) -> float:
    """Fraction of ``schema_fields`` with >=1 outgoing edge — покрытие (§10.5).

    Returns ``0.0`` for an empty field set (пустое множество полей) to avoid
    division by zero. Fields are deduplicated before the ratio is computed.
    """
    fields = tuple(dict.fromkeys(schema_fields))
    if not fields:
        return 0.0
    covered = sum(1 for name in fields if lineage.downstream_of(name))
    return covered / len(fields)
