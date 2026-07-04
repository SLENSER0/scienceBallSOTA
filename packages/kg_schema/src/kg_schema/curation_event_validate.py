"""Action-schema validation for CurationEvent records (§16.2 / §16.6).

Модель ``CurationEvent`` (§16) описывает одно кураторское действие над графом, но
сама по себе не проверяет, что *форма* события соответствует его ``action``: например,
слияние (``merge``) обязано нести список сливаемых идентификаторов и целевой канон, а
изменение схемы (``schema_change``) — новый термин. Этот модуль добавляет чистую
(pure) валидацию инвариантов id/цели и action-специфичных ``before``/``after`` форм.

:func:`validate_event` принимает «сырое» событие (``Mapping``) и возвращает неизменяемый
:class:`EventValidation` (``valid`` + список человекочитаемых ``errors``). Проверяются:

* ``id`` начинается с ``cur:``; ``actor_id`` — с ``user:`` (§16.2);
* ``target_type`` ∈ {node, edge, evidence, schema}; ``action`` ∈ 11-значного словаря;
* action-специфичные правила (§16.6) — см. :func:`required_keys` и ниже по коду.

This module enforces the CurationEvent action-schema (§16.2 / §16.6). The model exists,
but nothing checks that the ``before``/``after`` payload and id/target invariants match
the declared ``action``. :func:`validate_event` is pure — no store, no I/O — so it runs
during ingest, the curation API and CI alike.

Kuzu note: кастомные свойства узла ``:CurationEvent`` (``before`` / ``after`` / ``actor_id``)
НЕ являются запрашиваемыми колонками — их читают через ``get_node()``, в ``RETURN`` идут
только базовые колонки. Поэтому валидатор работает над плоским property-map, а не над
результатом Cypher-проекции.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# id / actor_id prefixes required by the CurationEvent contract (§16.2).
_ID_PREFIX = "cur:"
_ACTOR_PREFIX = "user:"

# The four legal curation targets (§16.2). Kept local so validation does not depend
# on a queryable Kuzu column — a CurationEvent's target_type is a stored property.
VALID_TARGET_TYPES: frozenset[str] = frozenset({"node", "edge", "evidence", "schema"})

# The 11 core curation actions (§16.6). Domain-specific actions (§24.20) are handled
# elsewhere; this vocabulary is the fixed set the action-schema rules below key off.
VALID_ACTIONS: tuple[str, ...] = (
    "accept",
    "reject",
    "correct",
    "merge",
    "split",
    "alias_add",
    "mark_inferred",
    "manual_evidence",
    "annotate",
    "schema_change",
    "deprecate",
)

# Targets for which a ``correct`` may be recorded (§16.6): a schema edit is a
# ``schema_change``, never a ``correct``.
_CORRECT_TARGETS: frozenset[str] = frozenset({"node", "edge", "evidence"})

# Minimum number of ids a ``merge`` must fold together (§16.6).
_MERGE_MIN_IDS = 2


@dataclass(frozen=True)
class EventValidation:
    """Outcome of validating one CurationEvent against the action-schema (§16.6).

    Attributes
    ----------
    valid:
        ``True`` iff ``errors`` is empty — the event satisfies every id/target
        invariant and its action-specific ``before``/``after`` shape.
    errors:
        Flat, human-readable list of every violation found (RU/EN messages). One
        pass collects *all* problems rather than stopping at the first.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§16.6).

        ``errors`` is copied so callers cannot mutate the frozen record through
        the returned mapping; ``as_dict()['errors']`` is always a ``list``.
        """
        return {"valid": self.valid, "errors": list(self.errors)}


def required_keys(action: str) -> tuple[str, ...]:
    """Top-level event keys that must be present and non-null for ``action`` (§16.6).

    Drives the generic ``before``/``after`` presence checks in
    :func:`validate_event` before the action-specific sub-key rules run:

    * ``merge`` / ``correct`` — both ``before`` and ``after`` are mandatory;
    * ``schema_change`` — only ``after`` (the new schema term) is mandatory;
    * every other action — no ``before``/``after`` key is structurally required.
    """
    if action in ("merge", "correct"):
        return ("before", "after")
    if action == "schema_change":
        return ("after",)
    return ()


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    """Return ``value`` if it is a mapping, else ``None`` (tolerant coercion)."""
    return value if isinstance(value, Mapping) else None


def _check_identity(event: Mapping[str, Any], errors: list[str]) -> None:
    """Validate id / actor_id / target_type / action invariants (§16.2)."""
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.startswith(_ID_PREFIX):
        errors.append(f"id must be a string starting with '{_ID_PREFIX}' (got {event_id!r})")

    actor_id = event.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id.startswith(_ACTOR_PREFIX):
        errors.append(
            f"actor_id must be a string starting with '{_ACTOR_PREFIX}' (got {actor_id!r})"
        )

    target_type = event.get("target_type")
    if target_type not in VALID_TARGET_TYPES:
        errors.append(
            f"target_type must be one of {sorted(VALID_TARGET_TYPES)} (got {target_type!r})"
        )

    action = event.get("action")
    if action not in VALID_ACTIONS:
        errors.append(f"action must be one of {list(VALID_ACTIONS)} (got {action!r})")


def _check_required_keys(event: Mapping[str, Any], action: str, errors: list[str]) -> None:
    """Ensure every key named by :func:`required_keys` is present and non-null (§16.6)."""
    for key in required_keys(action):
        if event.get(key) is None:
            errors.append(f"action '{action}' requires non-null '{key}'")


def _check_action_rules(event: Mapping[str, Any], action: str, errors: list[str]) -> None:
    """Apply the action-specific ``before``/``after`` and target rules (§16.6)."""
    target_type = event.get("target_type")
    before = _as_mapping(event.get("before"))
    after = _as_mapping(event.get("after"))

    if action == "merge":
        merged_ids = before.get("merged_ids") if before else None
        if not isinstance(merged_ids, (list, tuple)) or len(merged_ids) < _MERGE_MIN_IDS:
            errors.append(f"merge requires before['merged_ids'] with >= {_MERGE_MIN_IDS} ids")
        if not after or after.get("canonical_id") is None:
            errors.append("merge requires after['canonical_id']")

    elif action == "correct":
        # required_keys already flags null before/after; here we guard the target.
        if target_type not in _CORRECT_TARGETS:
            errors.append(
                f"correct requires target_type in {sorted(_CORRECT_TARGETS)} (got {target_type!r})"
            )

    elif action == "mark_inferred":
        if target_type != "edge":
            errors.append(f"mark_inferred requires target_type == 'edge' (got {target_type!r})")

    elif action == "manual_evidence":
        if target_type != "evidence":
            errors.append(
                f"manual_evidence requires target_type == 'evidence' (got {target_type!r})"
            )

    elif action == "schema_change":
        if target_type != "schema":
            errors.append(f"schema_change requires target_type == 'schema' (got {target_type!r})")
        if not after or not after.get("term"):
            errors.append("schema_change requires after['term']")


def validate_event(event: Mapping[str, Any]) -> EventValidation:
    """Validate one raw CurationEvent against the action-schema (§16.2 / §16.6).

    Collects *all* violations in one pass — id/actor/target/action invariants first,
    then the generic required-key presence checks, then the action-specific
    ``before``/``after`` and target rules — and returns a frozen
    :class:`EventValidation` whose ``valid`` flag is ``True`` iff no error was found.
    """
    errors: list[str] = []
    _check_identity(event, errors)

    action = event.get("action")
    if isinstance(action, str) and action in VALID_ACTIONS:
        _check_required_keys(event, action, errors)
        _check_action_rules(event, action, errors)

    return EventValidation(valid=not errors, errors=errors)


__all__ = [
    "VALID_ACTIONS",
    "VALID_TARGET_TYPES",
    "EventValidation",
    "required_keys",
    "validate_event",
]
