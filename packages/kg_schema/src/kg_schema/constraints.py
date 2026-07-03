"""Declared graph constraints + indexes catalog (§8.4 / §8.6).

Машинно-читаемый каталог (*machine-readable catalog*) декларативных ограничений графа:
уникальность идентификаторов (*id-uniqueness*) для всех меток узлов, полнотекстовый
индекс сущностей (*entity fulltext index*) и ключевые property-индексы. Каталог —
единственный источник правды (*single source of truth*), из которого выводятся и
Neo4j-миграции (``infra/neo4j/migrations``), и представление схемы во фронтенде (§8.6).

Каждый элемент — неизменяемая :class:`Constraint` с ``as_dict()``; метки берутся из
:mod:`kg_schema.labels` (``NodeLabel`` / ``RunLabel``), так что при расширении онтологии
каталог расширяется вместе с ней. :func:`to_cypher` печатает DDL профиля-сервера
(*server profile*) — ``CREATE CONSTRAINT`` / ``CREATE INDEX`` / ``CREATE FULLTEXT INDEX``
Neo4j, — а :func:`describe` отдаёт плоский список словарей для схемы-вью фронтенда.

Kuzu note: это ограничения профиля-сервера (Neo4j). На встроенном профиле (Kuzu)
кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()`` — поэтому property-/fulltext-индексы применимы только к серверному
бэкенду; каталог остаётся декларативным описанием намерения (*declared intent*).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from kg_schema.labels import NodeLabel, RunLabel


class ConstraintKind(StrEnum):
    """The four declared constraint / index kinds (§8.4)."""

    UNIQUE = "unique"  # node-key uniqueness — REQUIRE n.<prop> IS UNIQUE
    INDEX = "index"  # range / property index — ON (n.<prop>, ...)
    FULLTEXT = "fulltext"  # analyzed text index — ON EACH [n.<prop>, ...]
    EXISTS = "exists"  # existence constraint — REQUIRE n.<prop> IS NOT NULL


# The four kinds as plain strings, for cheap membership checks in callers / tests.
VALID_KINDS: frozenset[str] = frozenset(k.value for k in ConstraintKind)


@dataclass(frozen=True)
class Constraint:
    """One declared graph constraint or index (§8.4).

    Attributes
    ----------
    name:
        Stable DDL object name (e.g. ``"material_id"`` / ``"entity_name_index"``).
    kind:
        One of :class:`ConstraintKind` (``unique`` / ``index`` / ``fulltext`` /
        ``exists``).
    label:
        Target node label, or a pipe-joined label expression for a multi-label
        fulltext index (``"Material|Property|..."``).
    properties:
        The property (or properties) the object spans — ``("id",)`` for
        id-uniqueness, several for a fulltext / composite index.
    """

    name: str
    kind: str
    label: str
    properties: tuple[str, ...]

    @property
    def labels(self) -> tuple[str, ...]:
        """The concrete labels this object spans (``label`` split on ``|``)."""
        return tuple(self.label.split("|"))

    def key(self) -> tuple[str, tuple[str, ...], str]:
        """Identity used to detect duplicate ``(label, properties, kind)`` (§8.4)."""
        return (self.label, self.properties, self.kind)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict for the schema view (§8.6)."""
        return {
            "name": self.name,
            "kind": str(self.kind),
            "label": self.label,
            "labels": list(self.labels),
            "properties": list(self.properties),
        }


def _id_unique(label: NodeLabel | RunLabel) -> Constraint:
    """Build the ``id IS UNIQUE`` constraint for one node label (§8.4 / §3.10).

    Name mirrors the Neo4j migration convention ``<label-lower>_id`` (e.g.
    ``processingregime_id``), derived straight from the :mod:`kg_schema.labels` enum.
    """
    return Constraint(
        name=f"{str(label).lower()}_id",
        kind=ConstraintKind.UNIQUE,
        label=str(label),
        properties=("id",),
    )


# Every node label (core §8.1 + domain §24.2) plus provenance run labels (§8.2) carries a
# deterministic id (§3.10) — the uniqueness constraints are derived from the enum order.
_ID_LABELS: tuple[NodeLabel | RunLabel, ...] = (*NodeLabel, *RunLabel)

# §8.1 core node labels — the invariant tested for id-uniqueness coverage.
CORE_LABELS: tuple[NodeLabel, ...] = (
    NodeLabel.DOCUMENT,
    NodeLabel.PAPER,
    NodeLabel.SECTION,
    NodeLabel.PARAGRAPH,
    NodeLabel.TABLE,
    NodeLabel.FIGURE,
    NodeLabel.CHUNK,
    NodeLabel.EVIDENCE,
    NodeLabel.CLAIM,
    NodeLabel.FINDING,
    NodeLabel.EXPERIMENT,
    NodeLabel.SAMPLE,
    NodeLabel.MATERIAL,
    NodeLabel.ALLOY,
    NodeLabel.CHEMICAL_ELEMENT,
    NodeLabel.COMPOSITION,
    NodeLabel.PROCESSING_REGIME,
    NodeLabel.PROCESSING_STEP,
    NodeLabel.PARAMETER,
    NodeLabel.EQUIPMENT,
    NodeLabel.LAB,
    NodeLabel.RESEARCH_TEAM,
    NodeLabel.PERSON,
    NodeLabel.PROPERTY,
    NodeLabel.MEASUREMENT,
    NodeLabel.UNIT,
    NodeLabel.METHOD,
    NodeLabel.DATASET,
    NodeLabel.PROJECT,
    NodeLabel.DECISION,
    NodeLabel.CURATION_EVENT,
    NodeLabel.GAP,
    NodeLabel.CONTRADICTION,
)

# Labels covered by the entity fulltext index (§8.4) — the resolvable surface-form
# entities searched by ``entity_name_index``; ordered exactly as the Neo4j migration.
_ENTITY_FULLTEXT_LABELS: tuple[NodeLabel, ...] = (
    NodeLabel.MATERIAL,
    NodeLabel.PROPERTY,
    NodeLabel.EQUIPMENT,
    NodeLabel.LAB,
    NodeLabel.PERSON,
    NodeLabel.PROCESSING_REGIME,
    NodeLabel.TECHNOLOGY_SOLUTION,
)
_ENTITY_FULLTEXT_EXPR: str = "|".join(lbl.value for lbl in _ENTITY_FULLTEXT_LABELS)

# Key property / range indexes (§8.4) — numeric range access + fast facets (§3.11).
_PROPERTY_INDEXES: tuple[Constraint, ...] = (
    Constraint(
        "measurement_value_index",
        ConstraintKind.INDEX,
        NodeLabel.MEASUREMENT.value,
        ("value_normalized",),
    ),
    Constraint(
        "processing_temperature_index",
        ConstraintKind.INDEX,
        NodeLabel.PROCESSING_REGIME.value,
        ("temperature_c",),
    ),
    Constraint(
        "processing_time_index",
        ConstraintKind.INDEX,
        NodeLabel.PROCESSING_REGIME.value,
        ("time_h",),
    ),
    Constraint(
        "evidence_review_index", ConstraintKind.INDEX, NodeLabel.EVIDENCE.value, ("review_status",)
    ),
    Constraint("gap_type_index", ConstraintKind.INDEX, NodeLabel.GAP.value, ("gap_type",)),
    Constraint("paper_year_index", ConstraintKind.INDEX, NodeLabel.PAPER.value, ("year",)),
    Constraint(
        "tech_practice_index",
        ConstraintKind.INDEX,
        NodeLabel.TECHNOLOGY_SOLUTION.value,
        ("practice_type",),
    ),
)

# Fulltext indexes (§8.4 / §3.12) — analyzed RU/EN surface forms + evidence text.
_FULLTEXT_INDEXES: tuple[Constraint, ...] = (
    Constraint(
        "entity_name_index",
        ConstraintKind.FULLTEXT,
        _ENTITY_FULLTEXT_EXPR,
        ("name", "canonical_name", "aliases_text"),
    ),
    Constraint(
        "evidence_text_index",
        ConstraintKind.FULLTEXT,
        f"{NodeLabel.EVIDENCE.value}|{NodeLabel.CLAIM.value}",
        ("text",),
    ),
)

# The declared catalog (§8.4): id-uniqueness for every label, then property + fulltext
# indexes. Immutable — the single source of truth for migrations and the schema view.
CONSTRAINTS: tuple[Constraint, ...] = (
    *(_id_unique(lbl) for lbl in _ID_LABELS),
    *_PROPERTY_INDEXES,
    *_FULLTEXT_INDEXES,
)


def to_cypher(constraint: Constraint) -> str:
    """Emit the Neo4j server-profile DDL for one :class:`Constraint` (§8.4).

    Renders exactly one terminated statement (``... ;``) using ``IF NOT EXISTS`` so it is
    idempotent to re-apply. Uniqueness / existence emit ``CREATE CONSTRAINT``; range and
    fulltext emit ``CREATE INDEX`` / ``CREATE FULLTEXT INDEX``. Composite indexes list
    every property in order. Raises :class:`ValueError` for an unknown kind.
    """
    name, label, props = constraint.name, constraint.label, constraint.properties
    if constraint.kind == ConstraintKind.UNIQUE:
        return (
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{props[0]} IS UNIQUE;"
        )
    if constraint.kind == ConstraintKind.EXISTS:
        return (
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{props[0]} IS NOT NULL;"
        )
    if constraint.kind == ConstraintKind.INDEX:
        cols = ", ".join(f"n.{p}" for p in props)
        return f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON ({cols});"
    if constraint.kind == ConstraintKind.FULLTEXT:
        each = ", ".join(f"n.{p}" for p in props)
        return f"CREATE FULLTEXT INDEX {name} IF NOT EXISTS FOR (n:{label}) ON EACH [{each}];"
    raise ValueError(f"unknown constraint kind: {constraint.kind!r}")


def to_cypher_all() -> list[str]:
    """Every catalog statement as Cypher DDL, in declaration order (§8.4)."""
    return [to_cypher(c) for c in CONSTRAINTS]


def describe() -> list[dict[str, Any]]:
    """Flat catalog for the frontend schema view (§8.6).

    Each row is :meth:`Constraint.as_dict` enriched with its rendered ``cypher`` DDL, so
    the UI can show both the structured shape and the exact statement.
    """
    return [{**c.as_dict(), "cypher": to_cypher(c)} for c in CONSTRAINTS]


def constraint_names() -> list[str]:
    """All declared DDL object names, in declaration order (§8.4)."""
    return [c.name for c in CONSTRAINTS]


def constraints_by_kind(kind: str) -> list[Constraint]:
    """All catalog entries of one :class:`ConstraintKind` (§8.4)."""
    return [c for c in CONSTRAINTS if c.kind == kind]


__all__ = [
    "CONSTRAINTS",
    "CORE_LABELS",
    "VALID_KINDS",
    "Constraint",
    "ConstraintKind",
    "constraint_names",
    "constraints_by_kind",
    "describe",
    "to_cypher",
    "to_cypher_all",
]
