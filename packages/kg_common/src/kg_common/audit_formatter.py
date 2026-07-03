"""Audit-log formatting + redaction — форматирование журнала аудита (§19.11).

Every privileged action must leave a tamper-evident audit trail, and that trail
must never leak secrets or PII («записи аудита не должны содержать секретов»).
This module turns a raw ``(action, actor, target)`` event plus an optional
``detail`` mapping into a stable, JSON-friendly record and a one-line human view.

It builds *on top of* :mod:`kg_common.security.redaction` and never re-implements
masking: the ``detail`` payload is passed through :func:`redact_mapping`, so
sensitive keys (``password`` / ``token`` / ``api_key`` …) and free-text secrets
(bearer tokens, ``sk-…`` keys, JWTs, connection-string passwords) are masked
before they ever reach a log sink.

Everything is deterministic and side-effect free:

* No wall-clock — the timestamp ``at`` is always supplied by the caller
  (§19.11 «время передаётся явно»); the module never calls ``datetime.now``.
* No mutation — :func:`redact_mapping` returns a fresh structure, so the caller's
  ``detail`` dict is never touched.

Public API:

* :class:`AuditEntry`        — frozen ``{action, actor, target, at[, detail]}``
  record with :meth:`AuditEntry.as_dict`.
* :func:`format_audit_entry` — build a redacted audit record as a plain ``dict``.
* :func:`audit_line`         — render an entry as a single human-readable line.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kg_common.security import redact_mapping

__all__ = [
    "AuditEntry",
    "audit_line",
    "format_audit_entry",
]


def _normalize_at(at: str | datetime) -> str:
    """Render an explicit timestamp as a string — метка времени (§19.11).

    A :class:`~datetime.datetime` is serialized with :meth:`datetime.isoformat`;
    anything else is coerced with :func:`str`. The value is *always* provided by
    the caller — there is no wall-clock fallback («время передаётся явно»).
    """
    if isinstance(at, datetime):
        return at.isoformat()
    return str(at)


@dataclass(frozen=True)
class AuditEntry:
    """A single, immutable audit record — запись аудита (§19.11).

    ``action`` is the verb (e.g. ``"delete"``), ``actor`` the principal who did
    it (e.g. a user id), ``target`` the object acted upon (e.g. ``"node:42"``) and
    ``at`` the explicit ISO timestamp. ``detail`` is an *already-redacted* mapping
    of extra context, or ``None`` when there is none.

    The dataclass is frozen so an entry can be passed around and serialized
    safely; construction with redaction is done by :func:`format_audit_entry`.
    """

    action: str
    actor: str
    target: str
    at: str
    detail: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view — ``{action, actor, target, at[, detail]}`` (§19.11).

        The ``detail`` key is present only when a detail mapping was supplied, so
        an entry without extra context serializes to exactly four keys.
        """
        out: dict[str, Any] = {
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
            "at": self.at,
        }
        if self.detail is not None:
            out["detail"] = dict(self.detail)
        return out


def format_audit_entry(
    action: str,
    actor: str,
    target: str,
    *,
    detail: Mapping[str, Any] | None = None,
    at: str | datetime,
) -> dict[str, Any]:
    """Build a redacted audit record — сформировать запись аудита (§19.11).

    Returns a plain ``dict`` with ``action`` / ``actor`` / ``target`` / ``at`` and,
    when *detail* is given, a ``detail`` sub-mapping that has been run through
    :func:`redact_mapping` — so no secret or PII survives into the record. *at*
    is keyword-only and required: the caller always supplies the timestamp
    (§19.11), keeping the function deterministic and free of wall-clock reads. The
    input *detail* is never mutated.
    """
    redacted = None if detail is None else redact_mapping(dict(detail))
    entry = AuditEntry(
        action=str(action),
        actor=str(actor),
        target=str(target),
        at=_normalize_at(at),
        detail=redacted,
    )
    return entry.as_dict()


def _render_detail(detail: Mapping[str, Any]) -> str:
    """Render a detail mapping as sorted ``key=value`` pairs — детали (§19.11)."""
    return " ".join(f"{k}={detail[k]}" for k in sorted(detail))


def audit_line(entry: Mapping[str, Any]) -> str:
    """Render an audit *entry* as one human-readable line — строка аудита (§19.11).

    Accepts the mapping produced by :func:`format_audit_entry` and formats it as
    ``"<at> <actor> <action> <target>"``; when the entry carries a non-empty
    ``detail`` mapping its keys are appended as sorted ``key=value`` pairs. The
    rendering is deterministic — the same entry always yields the same line.
    """
    line = f"{entry['at']} {entry['actor']} {entry['action']} {entry['target']}"
    detail = entry.get("detail")
    if detail:
        line = f"{line} {_render_detail(detail)}"
    return line
