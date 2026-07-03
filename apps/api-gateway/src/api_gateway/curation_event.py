"""Канонический строитель :class:`CurationEvent` из §12.3 (§14.14).

Каждая мутация графа знаний (merge/split/alias/accept/…) обязана записать одно
и то же событие кураторства с фиксированным набором из десяти полей §12.3. Раньше
каждый эндпоинт собирал этот словарь вручную, что вело к рассинхрону имён полей и
непроверенным глаголам действия. Этот модуль даёт единый неизменяемый тип события
и валидирующий фабричный метод, разделяемые всеми мутациями. Чистый stdlib,
детерминированно (кроме автозаполнения ``event_id``/``created_at``), без сети.

The canonical §12.3 curation-event builder shared across every knowledge-graph
mutation. Every mutation must record the same ten-field §12.3 event; previously
each endpoint hand-assembled that dict, drifting on field names and skipping
action-verb validation. This module supplies one frozen event type plus a
validating factory shared by all mutations. Pure stdlib, deterministic apart
from ``event_id``/``created_at`` auto-fill, no I/O.

* :data:`VALID_ACTIONS` — frozen set of the eleven §12.3 curation verbs.
* :class:`CurationEvent` — frozen ten-field event with :meth:`as_dict`.
* :func:`build_event` — validating factory that auto-fills id/timestamp.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "VALID_ACTIONS",
    "CurationEvent",
    "build_event",
]

# Допустимые глаголы кураторства — accepted curation verbs (§12.3).
VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "merge",
        "split",
        "alias_add",
        "accept",
        "reject",
        "correct",
        "schema_change",
        "mark_inferred",
        "manual_evidence",
        "gap_annotate",
        "experiment_verify",
    }
)

# Порядок полей §12.3 — canonical §12.3 field order for ``as_dict``.
_FIELDS: tuple[str, ...] = (
    "event_id",
    "actor_id",
    "action",
    "target_type",
    "target_id",
    "before",
    "after",
    "reason",
    "created_at",
    "request_id",
)


@dataclass(frozen=True, slots=True)
class CurationEvent:
    """Неизменяемое событие кураторства с десятью полями §12.3 (§14.14).

    Immutable §12.3 curation event. ``action`` is one of :data:`VALID_ACTIONS`;
    ``before``/``after`` are the pre/post state snapshots; ``request_id`` ties the
    event to the originating HTTP request (``None`` when unknown). Field defaults
    exist only so :meth:`as_dict` order stays stable; construct via
    :func:`build_event` for validation and id/timestamp auto-fill.
    """

    event_id: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    created_at: str = ""
    request_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление события — ровно десять полей §12.3 (§14.14).

        Возвращает поля в каноническом порядке §12.3, пригодном для записи в
        аудит и сериализации без потери имён.

        Returns the ten §12.3 fields in canonical order, audit-ready and safe to
        serialize without name drift.
        """
        return {name: getattr(self, name) for name in _FIELDS}


def build_event(
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    request_id: str | None = None,
    event_id: str | None = None,
    created_at: str | None = None,
) -> CurationEvent:
    """Собрать проверенное событие кураторства §12.3 (§14.14).

    Проверяет, что ``action`` входит в :data:`VALID_ACTIONS`; при отсутствии
    ``event_id``/``created_at`` подставляет непустой UUID и UTC-метку времени
    ISO-8601. ``before``/``after`` по умолчанию — пустые словари.

    Validate ``action`` against :data:`VALID_ACTIONS`, then auto-fill a non-empty
    UUID ``event_id`` and an ISO-8601 UTC ``created_at`` when omitted;
    ``before``/``after`` default to empty dicts.

    :raises ValueError: если ``action`` не входит в :data:`VALID_ACTIONS`.
    :raises ValueError: when ``action`` is not a §12.3 curation verb.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown curation action: {action!r}")
    return CurationEvent(
        event_id=event_id if event_id is not None else uuid.uuid4().hex,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=dict(before) if before is not None else {},
        after=dict(after) if after is not None else {},
        reason=reason,
        created_at=(created_at if created_at is not None else datetime.now(UTC).isoformat()),
        request_id=request_id,
    )
