"""Gap aging & SLA-breach classification — store-free (§15.9/§15.2).

A *knowledge gap* is a curator work item: something the graph is missing or
under-covered (an empty ``(material, property)`` cell, a dangling entity, a
low-recall query). Once *detected*, a gap sits in a queue until it is
``resolved`` or ``dismissed``. The longer an **open** gap waits, the staler the
knowledge base — so each severity gets a service-level agreement (SLA): a budget
of days within which the gap should be closed. Старение (aging) измеряет, как
долго пробел открыт, и нарушен ли SLA.

This module is a thin, read-only *classification* layer over already-detected
gaps (plain dicts, each ``{id, severity, status, detected_at}`` where
``detected_at`` is an ISO 8601 string). Given a reference ``now`` it computes,
per gap, an :class:`GapAge`: the open **age** in days, the severity's **SLA**
budget, whether the SLA is **breached**, and by how many days it is **overdue**.

Rules:

- Only ``status == "open"`` gaps age. A ``resolved`` / ``dismissed`` gap is done,
  so it never breaches (``breached=False``, ``overdue_days=0.0``) — but we still
  report its age for auditing.
- The SLA budget is keyed by severity (:data:`SLA_DAYS`); an unknown severity
  falls back to :data:`DEFAULT_SLA_DAYS` (30) rather than raising.
- A malformed / missing ``detected_at`` cannot be aged, so ``age_days`` is
  ``0.0`` and the gap is treated as not breached (fail-safe, never crash).

:func:`aging_report` runs :func:`age_of` over a batch and sorts by
``overdue_days`` descending, so the most-overdue breaches surface first. No
graph, no store, no writes — pure Python over dicts and datetimes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from kg_common import get_logger

_log = get_logger("gap_aging")

# Severity → SLA budget in days. Higher severity ⇒ tighter deadline (§15.2).
SLA_DAYS: dict[str, int] = {"critical": 3, "high": 7, "medium": 30, "low": 90}

# Fallback budget for an unknown / missing severity (без известного уровня).
DEFAULT_SLA_DAYS = 30

# Statuses that still age toward their SLA. Everything else is "done".
_OPEN_STATUS = "open"


@dataclass(frozen=True, slots=True)
class GapAge:
    """Aging verdict for a single gap (замороженный результат старения)."""

    gap_id: str
    severity: str
    age_days: float
    sla_days: int
    breached: bool
    overdue_days: float

    def as_dict(self) -> dict[str, Any]:
        """Serialise all six fields to a plain dict (round-trips 1:1)."""
        return asdict(self)


def _parse_detected_at(raw: Any) -> datetime | None:
    """Parse an ISO 8601 ``detected_at`` string, or ``None`` if malformed."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # Tolerate a trailing "Z" (UTC) which ``fromisoformat`` accepts only
        # from 3.11+; normalise defensively for older-style inputs.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _sla_for(severity: Any) -> int:
    """Look up the SLA budget for ``severity``, falling back to the default."""
    if isinstance(severity, str):
        return SLA_DAYS.get(severity.lower(), DEFAULT_SLA_DAYS)
    return DEFAULT_SLA_DAYS


def age_of(gap: dict[str, Any], now: datetime) -> GapAge:
    """Classify one gap's age and SLA status against reference ``now``.

    Only ``status == "open"`` gaps can breach; ``resolved`` / ``dismissed``
    gaps return ``breached=False`` and ``overdue_days=0.0`` regardless of age. A
    malformed / missing ``detected_at`` yields ``age_days=0.0`` and no breach.
    """
    gap_id = str(gap.get("id", ""))
    severity = gap.get("severity", "")
    severity_str = severity if isinstance(severity, str) else str(severity)
    status = gap.get("status", "")
    sla_days = _sla_for(severity)

    detected = _parse_detected_at(gap.get("detected_at"))
    if detected is None:
        # Cannot age an undated gap — fail safe, never breach (§15.9).
        _log.debug("gap %s has malformed detected_at; age=0", gap_id)
        return GapAge(gap_id, severity_str, 0.0, sla_days, False, 0.0)

    age_days = (now - detected).total_seconds() / 86400.0
    is_open = isinstance(status, str) and status.lower() == _OPEN_STATUS
    if is_open:
        overdue = age_days - sla_days
        breached = overdue > 0.0
        overdue_days = overdue if breached else 0.0
    else:
        breached = False
        overdue_days = 0.0
    return GapAge(gap_id, severity_str, age_days, sla_days, breached, overdue_days)


def aging_report(gaps: list[dict[str, Any]], now: datetime) -> list[GapAge]:
    """Age every gap and sort by ``overdue_days`` descending (worst first)."""
    ages = [age_of(gap, now) for gap in gaps]
    ages.sort(key=lambda a: a.overdue_days, reverse=True)
    return ages
