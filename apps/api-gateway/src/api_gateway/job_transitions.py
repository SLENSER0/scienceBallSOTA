"""Ingest job lifecycle state machine + idempotent cancel (§14.10).

Чистая машина состояний над статусами ingest-задач ``queued/running/
succeeded/failed/cancelled``. Никаких обращений к БД или сети — только
предвычисленная таблица разрешённых переходов и правило идемпотентной
отмены (409/200): активную задачу отменяем один раз (``changed``), а
повторная отмена уже завершённой задачи — конфликт без изменения статуса.

Pure lifecycle state machine over ingest-job statuses. No DB / network —
just a precomputed transition table and the idempotent-cancel rule (the
409/200 contract). Public surface:

* :data:`ALLOWED`            — ``src -> frozenset(dst)`` transition table.
* :data:`TERMINAL`           — terminal statuses (no outgoing edges).
* :func:`is_terminal`        — is a status terminal?
* :func:`can_transition`     — is ``src -> dst`` allowed?
* :func:`validate_transition`— assert a transition or raise.
* :class:`InvalidTransition` — raised on a disallowed transition.
* :class:`CancelOutcome`     — frozen result of :func:`cancel`.
* :func:`cancel`             — idempotent cancel over the current status.
"""

from __future__ import annotations

from dataclasses import dataclass

# Все статусы жизненного цикла задачи / all lifecycle statuses.
STATUSES: frozenset[str] = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})

# Терминальные статусы — из них нет исходящих переходов (§14.10).
TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})

# Таблица разрешённых переходов / allowed ``src -> {dst}`` transitions.
ALLOWED: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class InvalidTransition(ValueError):
    """Недопустимый переход состояния / a disallowed lifecycle transition."""


def is_terminal(status: str) -> bool:
    """Терминален ли статус / is ``status`` a terminal state (§14.10)."""
    return status in TERMINAL


def can_transition(src: str, dst: str) -> bool:
    """Разрешён ли переход ``src -> dst`` / is the transition allowed."""
    return dst in ALLOWED.get(src, frozenset())


def validate_transition(src: str, dst: str) -> None:
    """Проверить переход или бросить / assert ``src -> dst`` or raise.

    :raises InvalidTransition: если переход не входит в :data:`ALLOWED`.
    """
    if not can_transition(src, dst):
        raise InvalidTransition(f"illegal transition: {src!r} -> {dst!r}")


@dataclass(frozen=True)
class CancelOutcome:
    """Результат идемпотентной отмены / result of an idempotent cancel.

    ``status`` — итоговый статус задачи, ``changed`` — была ли задача реально
    переведена в ``cancelled``, ``conflict`` — попытка отменить уже
    завершённую задачу (моделирует ответ 409; ``changed=True`` -> 200).
    """

    status: str
    changed: bool
    conflict: bool

    def as_dict(self) -> dict:
        """Return ``{"status", "changed", "conflict"}``."""
        return {"status": self.status, "changed": self.changed, "conflict": self.conflict}


def cancel(current: str) -> CancelOutcome:
    """Идемпотентно отменить задачу / idempotently cancel a job (§14.10).

    ``queued``/``running`` -> статус ``cancelled``, ``changed=True``,
    ``conflict=False`` (200). Уже терминальная задача -> статус без
    изменений, ``changed=False``, ``conflict=True`` (409).
    """
    if is_terminal(current):
        return CancelOutcome(status=current, changed=False, conflict=True)
    return CancelOutcome(status="cancelled", changed=True, conflict=False)
