"""§3.19 — validate an edge *dict* against the declarative edge schema (pure Python).

Валидация связи (*relation validation*): проверяет, что плоский словарь ребра вида
``{"source_label", "rel_type", "target_label"}`` описывает тройку, объявленную в
:data:`kg_schema.relationships.EDGE_SCHEMA` (§3.19). Модуль строится ПОВЕРХ
``relationships.py`` — переиспользует :data:`EDGE_SCHEMA` и
:func:`kg_schema.relationships.is_valid_edge` и ничего в них не переопределяет.

Отличие от :mod:`kg_schema.edge_guard` (§3.16): там страж принимает три *позиционных*
аргумента и поднимает исключение на upsert; здесь — чистая функция над ``dict`` (например,
ребром из LLM-экстракции), которая возвращает структурированный результат с человекочитаемой
причиной (*reason*) вместо исключения, удобный для батч-отчётов и телеметрии.

* :func:`validate_relation` → :class:`RelationValidation` (``ok`` / ``reason``): валидная
  тройка → ``ok=True`` с пустым ``reason``; иначе ``ok=False`` и ``reason`` называет
  конкретную проблему (отсутствующее поле, неизвестный ``rel_type``, недопустимая цель).
* :func:`allowed_relations_from` — отсортированный набор пар ``(rel_type, target_label)``,
  разрешённых для метки-источника (виртуальная метка ``Entity`` разворачивается в
  :data:`kg_schema.labels.ENTITY_LABELS`, как и в ``is_valid_edge``).

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()`` (в ``RETURN`` идут только базовые колонки). Проверка работает над уже
собранным ``dict`` ребра (метки источника/цели входят в базовые колонки), а не над
Cypher-``RETURN`` пользовательских свойств.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kg_schema.labels import ENTITY_LABELS
from kg_schema.relationships import EDGE_SCHEMA, ENTITY, is_valid_edge

# Keys a well-formed edge dict must carry (§3.19), in stable report order.
REQUIRED_FIELDS: tuple[str, ...] = ("source_label", "rel_type", "target_label")

# Every relationship type that appears in a declared signature (§3.5 / §3.19).
KNOWN_REL_TYPES: frozenset[str] = frozenset(r for _f, r, _t in EDGE_SCHEMA)


@dataclass(frozen=True)
class RelationValidation:
    """Immutable result of validating one edge dict against the schema (§3.19).

    Attributes
    ----------
    ok:
        ``True`` iff the edge dict has all required fields and its
        ``(source_label, rel_type, target_label)`` triple is a declared signature.
    reason:
        Human-readable explanation of the rejection, or ``""`` when :attr:`ok`.
    """

    ok: bool
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.19)."""
        return {"ok": self.ok, "reason": self.reason}


def _expand(label: str) -> set[str]:
    """Expand the virtual ``Entity`` label to concrete :data:`ENTITY_LABELS`."""
    return set(ENTITY_LABELS) if label == ENTITY else {label}


def _is_missing(edge: Mapping[str, Any], field: str) -> bool:
    """A field is missing if absent, ``None``, or a blank string (§3.19)."""
    if field not in edge:
        return True
    value = edge[field]
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _allowed_targets(source_label: str, rel_type: str) -> list[str]:
    """Sorted concrete ``target_label`` values allowed for ``(source, rel)`` (§3.19)."""
    targets: set[str] = set()
    for f, r, t in EDGE_SCHEMA:
        if r == rel_type and source_label in _expand(f):
            targets |= _expand(t)
    return sorted(targets)


def allowed_relations_from(label: str) -> list[tuple[str, str]]:
    """Return the sorted ``(rel_type, target_label)`` pairs allowed from ``label`` (§3.19).

    Scans :data:`EDGE_SCHEMA` for signatures whose source matches ``label`` (with
    ``Entity`` expansion) and collects each ``(rel_type, concrete target)`` pair; a
    ``target`` of ``Entity`` expands to :data:`ENTITY_LABELS`. An unknown label yields
    ``[]``. Membership matches :func:`validate_relation`: a pair is in this list iff the
    corresponding edge dict validates ``ok``.
    """
    pairs: set[tuple[str, str]] = set()
    for f, r, t in EDGE_SCHEMA:
        if label in _expand(f):
            for target in _expand(t):
                pairs.add((r, target))
    return sorted(pairs)


def validate_relation(edge: Mapping[str, Any]) -> RelationValidation:
    """Validate one edge dict against :data:`EDGE_SCHEMA` (§3.19).

    ``edge`` must carry :data:`REQUIRED_FIELDS`. On success returns
    ``RelationValidation(ok=True, reason="")``. On failure ``ok`` is ``False`` and
    ``reason`` names the first problem found, in this order:

    * a missing / blank required field,
    * an unknown ``rel_type`` (no declared signature uses it),
    * a source label with no outgoing edge of that ``rel_type``,
    * an otherwise-valid ``(source, rel)`` with a target outside its allowed set.
    """
    for field in REQUIRED_FIELDS:
        if _is_missing(edge, field):
            return RelationValidation(ok=False, reason=f"missing required field: {field!r}")

    source = str(edge["source_label"])
    rel = str(edge["rel_type"])
    target = str(edge["target_label"])

    if is_valid_edge(source, rel, target):
        return RelationValidation(ok=True)

    if rel not in KNOWN_REL_TYPES:
        return RelationValidation(ok=False, reason=f"unknown rel_type: {rel!r}")

    allowed = _allowed_targets(source, rel)
    if not allowed:
        return RelationValidation(ok=False, reason=f"{source!r} has no outgoing {rel} relation")
    return RelationValidation(
        ok=False,
        reason=f"invalid target {target!r} for {source}-[:{rel}]->; allowed: {allowed}",
    )


__all__ = [
    "KNOWN_REL_TYPES",
    "REQUIRED_FIELDS",
    "RelationValidation",
    "allowed_relations_from",
    "validate_relation",
]
