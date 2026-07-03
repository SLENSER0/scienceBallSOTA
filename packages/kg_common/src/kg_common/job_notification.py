"""UI notifications for terminal ingest jobs — уведомления о задачах (§9.10).

When an ingest job reaches a terminal state the pipeline emits a structured
notification onto the notifications queue so the UI can surface it. This module
is pure — детерминизм: no I/O, no clock. It models one notification via the
frozen :class:`JobNotification` and derives it from a terminal job status with
:func:`for_status`. :func:`should_notify` is the single gate deciding whether a
status warrants a notification (only terminal statuses do).

The *event* mirrors the terminal status (``succeeded`` / ``failed`` /
``canceled``) and the UI *level* is derived from it: a failure is an ``error``,
a cancellation a ``warning`` and a success an ``info``. Failure notifications
embed the error text so the message is actionable — сообщение с текстом ошибки.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "JobNotification",
    "TERMINAL_STATUSES",
    "VALID_EVENTS",
    "for_status",
    "should_notify",
]

# Terminal ingest-job statuses — терминальные статусы (§9.10). Only these
# warrant a UI notification; ``queued`` / ``running`` are in-flight.
TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "canceled"})

# The events a notification may carry — допустимые события. Equal to the
# terminal statuses: the event mirrors the status that produced it.
VALID_EVENTS: frozenset[str] = TERMINAL_STATUSES

# Event -> UI level — уровень выводится из события (§9.10).
_EVENT_LEVEL: dict[str, str] = {
    "succeeded": "info",
    "failed": "error",
    "canceled": "warning",
}


@dataclass(frozen=True, slots=True)
class JobNotification:
    """One UI notification for a terminal ingest job — уведомление (§9.10).

    ``job_id`` identifies the job (non-empty). ``event`` is one of
    :data:`VALID_EVENTS`. ``level`` is the derived UI severity (``info`` /
    ``warning`` / ``error``) and must match the event's mapping. ``message`` is
    a human-readable line. ``doc_id`` is the affected document if known.
    """

    job_id: str
    event: str
    level: str
    message: str
    doc_id: str | None = None

    def __post_init__(self) -> None:
        """Validate id, event and derived level — валидация полей (§9.10)."""
        if not self.job_id or not self.job_id.strip():
            raise ValueError("job_id must be a non-empty string")
        if self.event not in VALID_EVENTS:
            raise ValueError(f"event must be one of {sorted(VALID_EVENTS)}, got {self.event!r}")
        expected = _EVENT_LEVEL[self.event]
        if self.level != expected:
            raise ValueError(
                f"level for event {self.event!r} must be {expected!r}, got {self.level!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "job_id": self.job_id,
            "event": self.event,
            "level": self.level,
            "message": self.message,
            "doc_id": self.doc_id,
        }


def should_notify(status: str) -> bool:
    """True iff ``status`` is terminal — стоит ли уведомлять (§9.10).

    Returns ``True`` only for :data:`TERMINAL_STATUSES` (``succeeded`` /
    ``failed`` / ``canceled``); ``queued`` / ``running`` or any other value
    yield ``False``. This is the single gate the pipeline consults before
    building a notification.
    """
    return status in TERMINAL_STATUSES


def for_status(
    job_id: str,
    status: str,
    *,
    doc_id: str | None = None,
    error: str | None = None,
) -> JobNotification:
    """Build a notification for a terminal status — уведомление по статусу (§9.10).

    ``status`` must be a terminal status (see :func:`should_notify`); a
    non-terminal or unknown value raises :class:`ValueError`. The event mirrors
    the status and the level is derived from it. For ``failed`` the ``error``
    text, when given, is embedded into the message so the UI line is actionable.
    """
    if status not in TERMINAL_STATUSES:
        raise ValueError(
            f"status must be terminal, one of {sorted(TERMINAL_STATUSES)}, got {status!r}"
        )
    level = _EVENT_LEVEL[status]
    doc_suffix = f" for {doc_id}" if doc_id else ""
    if status == "succeeded":
        message = f"Ingest job {job_id}{doc_suffix} succeeded"
    elif status == "canceled":
        message = f"Ingest job {job_id}{doc_suffix} was canceled"
    else:  # failed
        detail = f": {error}" if error else ""
        message = f"Ingest job {job_id}{doc_suffix} failed{detail}"
    return JobNotification(
        job_id=job_id,
        event=status,
        level=level,
        message=message,
        doc_id=doc_id,
    )
