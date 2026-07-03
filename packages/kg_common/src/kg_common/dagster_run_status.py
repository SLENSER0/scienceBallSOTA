"""Dagster run-status sync — синхронизация статуса ранов (§9.9).

The ``run_status_sensor`` observes a Dagster run and mirrors its lifecycle onto
the ``ingest_jobs.status`` domain. Two concerns live here, both pure:

* :func:`to_job_status` — translate a :class:`DagsterRunStatus` name onto our
  own status vocabulary («перевод статуса Dagster в домен ingest_jobs»).
* :func:`transition`    — enforce a legal state-machine: once a job reaches a
  **terminal** state (``succeeded`` / ``failed`` / ``canceled``) it may never
  move again — «из терминального состояния выхода нет».

The Dagster → domain mapping is:

* ``QUEUED``                → ``queued``
* ``STARTING`` / ``STARTED`` → ``running``
* ``SUCCESS``                → ``succeeded``
* ``FAILURE``                → ``failed``
* ``CANCELED`` / ``CANCELING`` → ``canceled``

Any other Dagster name raises :class:`ValueError`. Everything here is
deterministic and side-effect free — no store, no clock.

Public API:

* :class:`StatusTransition` — frozen verdict with :meth:`StatusTransition.as_dict`.
* :func:`to_job_status`     — Dagster name → domain status.
* :func:`is_terminal`       — terminal-state predicate.
* :func:`transition`        — legal-move state-machine verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "StatusTransition",
    "is_terminal",
    "to_job_status",
    "transition",
]

# Domain statuses of ingest_jobs.status — домен статусов (§9.9).
_QUEUED = "queued"
_RUNNING = "running"
_SUCCEEDED = "succeeded"
_FAILED = "failed"
_CANCELED = "canceled"

_JOB_STATUSES: frozenset[str] = frozenset({_QUEUED, _RUNNING, _SUCCEEDED, _FAILED, _CANCELED})

# Terminal statuses — терминальные состояния (§9.9).
_TERMINAL: frozenset[str] = frozenset({_SUCCEEDED, _FAILED, _CANCELED})

# DagsterRunStatus name → domain status — карта Dagster → домен.
_DAGSTER_TO_JOB: dict[str, str] = {
    "QUEUED": _QUEUED,
    "STARTING": _RUNNING,
    "STARTED": _RUNNING,
    "SUCCESS": _SUCCEEDED,
    "FAILURE": _FAILED,
    "CANCELED": _CANCELED,
    "CANCELING": _CANCELED,
}


@dataclass(frozen=True, slots=True)
class StatusTransition:
    """Immutable transition verdict — неизменяемый вердикт перехода (§9.9).

    ``from_status`` / ``to_status`` are the two domain statuses, ``allowed`` is
    the legality decision and ``terminal`` reports whether ``from_status`` was
    already terminal — «источник терминален?».
    """

    from_status: str
    to_status: str
    allowed: bool
    terminal: bool

    def as_dict(self) -> dict[str, object]:
        """Return a plain-dict view — словарь для сериализации."""
        return {
            "from_status": self.from_status,
            "to_status": self.to_status,
            "allowed": self.allowed,
            "terminal": self.terminal,
        }


def to_job_status(dagster_status: str) -> str:
    """Map a ``DagsterRunStatus`` name onto ``ingest_jobs.status`` (§9.9).

    Raises :class:`ValueError` for an unknown Dagster status —
    «неизвестный статус Dagster».
    """
    try:
        return _DAGSTER_TO_JOB[dagster_status]
    except KeyError:
        raise ValueError(f"unknown DagsterRunStatus: {dagster_status!r}") from None


def is_terminal(job_status: str) -> bool:
    """Return ``True`` for a terminal domain status — терминальность (§9.9).

    Raises :class:`ValueError` for a status outside the domain.
    """
    if job_status not in _JOB_STATUSES:
        raise ValueError(f"unknown job status: {job_status!r}")
    return job_status in _TERMINAL


def transition(from_status: str, to_status: str) -> StatusTransition:
    """Judge a status move against the state-machine — легальность перехода.

    A move **out of** a terminal ``from_status`` is always disallowed; any
    move between non-terminal states (e.g. ``queued`` → ``running``) is allowed.
    Both statuses must belong to the domain else :class:`ValueError` is raised.
    """
    terminal = is_terminal(from_status)
    # Validate destination too — пункт назначения тоже в домене.
    _ = is_terminal(to_status)
    allowed = not terminal
    return StatusTransition(
        from_status=from_status,
        to_status=to_status,
        allowed=allowed,
        terminal=terminal,
    )
