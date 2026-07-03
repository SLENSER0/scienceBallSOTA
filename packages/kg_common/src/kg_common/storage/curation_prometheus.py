"""Curation Prometheus metric family (§16.11 семейство метрик курации).

Where :mod:`kg_common.storage.review_metrics` yields a *generic*
:class:`~kg_common.storage.review_metrics.QueueMetrics` snapshot, this module emits
the **named §16.11 Prometheus series** the curation dashboard scrapes. It is a pure
transform over *task rows* — no store, no I/O, no wall clock read inside the logic.
The current instant ``now_iso`` is passed in by the caller as an ISO-8601 string so
every number is deterministic and hand-checkable (детерминированность).

Row shape (форма строки задачи) — a plain mapping::

    {"status": "open" | "resolved" | "auto_resolved",  # жизненный цикл задачи
     "task_type": "contradiction",                      # тип задачи (ключ resolved_total)
     "created_at": "2026-01-01T00:00:00",               # ISO-8601, момент постановки
     "auto_resolved": True}                             # optional flag, alt to status

A task is counted **auto-resolved** when ``status == "auto_resolved"`` *or* the
optional ``auto_resolved`` flag is truthy; a task with ``status == "resolved"`` (and
no auto flag) is a **manual** resolution. ``resolved_total`` is the histogram over
*every* resolved task (manual + auto) keyed by ``task_type``. ``auto_resolved_ratio``
is ``auto / (manual + auto)`` — the share of resolutions the system closed itself,
and ``0.0`` (not a ``ZeroDivisionError``) when nothing has been resolved.

The p95 backlog age (``review_backlog_age_p95``) is a **nearest-rank** percentile of
the *open* backlog's ages in hours, measured from ``now_iso``; aging is defined
identically to §16.4 via :func:`kg_common.storage.review_priority.age_hours`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from kg_common.storage.review_priority import age_hours

# -- task lifecycle statuses (mirror §16.4 review_queue) -------------------
STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
STATUS_AUTO_RESOLVED = "auto_resolved"

_P95 = 95.0  # перцентиль возраста бэклога (§16.11)
_AGE_PRECISION = 6  # округление часов (гасим шум float в отображении)
_RATIO_PRECISION = 6  # округление доли авто-резолвов


def _is_auto(task: Mapping[str, Any]) -> bool:
    """Whether ``task`` was auto-resolved — по статусу или по флагу ``auto_resolved``."""
    if task.get("status") == STATUS_AUTO_RESOLVED:
        return True
    return bool(task.get("auto_resolved"))


def _is_resolved(task: Mapping[str, Any]) -> bool:
    """Whether ``task`` has left the queue (manual или auto резолв)."""
    return task.get("status") in (STATUS_RESOLVED, STATUS_AUTO_RESOLVED) or _is_auto(task)


def _percentile_nearest_rank(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile of ``values`` (метод ближайшего ранга, §16.11).

    Sorts ascending, takes the value at 1-based rank ``ceil(pct/100 * n)``. Returns
    ``0.0`` for an empty input. For ``[1, 2, 100]`` at p95 the rank is
    ``ceil(0.95 * 3) == 3`` → ``100.0``.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


@dataclass(frozen=True)
class CurationMetrics:
    """Named §16.11 curation series — снимок метрик курации.

    Fields
    ------
    tasks_open:
        Open backlog size (``status == "open"``) — открытые задачи.
    resolved_total:
        ``{task_type: count}`` over every resolved task, manual + auto
        (гистограмма закрытий по типу), sorted by ``task_type``.
    verified_fields_protected_total:
        Verified fields shielded from overwrite (защищённые поля, §16.11), taken from
        the caller's ``protected_count``.
    review_backlog_age_p95:
        Nearest-rank p95 age-in-hours of the open backlog; ``0.0`` when empty.
    auto_resolved_ratio:
        ``auto / (manual + auto)`` share of auto-resolutions; ``0.0`` when nothing is
        resolved (no ``ZeroDivisionError``).
    """

    tasks_open: int
    resolved_total: Mapping[str, int]
    verified_fields_protected_total: int
    review_backlog_age_p95: float
    auto_resolved_ratio: float

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (JSON-friendly, ``resolved_total`` copied)."""
        return {
            "tasks_open": self.tasks_open,
            "resolved_total": dict(self.resolved_total),
            "verified_fields_protected_total": self.verified_fields_protected_total,
            "review_backlog_age_p95": self.review_backlog_age_p95,
            "auto_resolved_ratio": self.auto_resolved_ratio,
        }


def compute(
    tasks: Sequence[Mapping[str, Any]],
    *,
    now_iso: str,
    protected_count: int = 0,
) -> CurationMetrics:
    """Aggregate ``tasks`` into a :class:`CurationMetrics` as of ``now_iso`` (§16.11).

    ``now_iso`` is an explicit ISO-8601 instant (детерминированность — no wall clock
    is read). Open tasks feed ``tasks_open`` and the p95 backlog age; resolved tasks
    (manual + auto) feed ``resolved_total`` by ``task_type``; ``auto_resolved_ratio``
    divides auto by all resolutions. ``protected_count`` is surfaced verbatim as
    ``verified_fields_protected_total``. See the module docstring for the row shape.
    """
    tasks_open = 0
    manual_resolved = 0
    auto_resolved = 0
    resolved_total: dict[str, int] = {}
    open_ages: list[float] = []
    for task in tasks:
        if task.get("status") == STATUS_OPEN:
            tasks_open += 1
            created_at = task.get("created_at")
            if created_at:
                open_ages.append(age_hours(str(created_at), now_iso))
            continue
        if _is_resolved(task):
            task_type = str(task.get("task_type", ""))
            resolved_total[task_type] = resolved_total.get(task_type, 0) + 1
            if _is_auto(task):
                auto_resolved += 1
            else:
                manual_resolved += 1
    total_resolved = manual_resolved + auto_resolved
    ratio = round(auto_resolved / total_resolved, _RATIO_PRECISION) if total_resolved else 0.0
    p95 = round(_percentile_nearest_rank(open_ages, _P95), _AGE_PRECISION)
    return CurationMetrics(
        tasks_open=tasks_open,
        resolved_total=dict(sorted(resolved_total.items())),
        verified_fields_protected_total=int(protected_count),
        review_backlog_age_p95=p95,
        auto_resolved_ratio=ratio,
    )


def _fmt(value: float) -> str:
    """Render a metric value — целые без ``.0``, дробные как есть (Prometheus-friendly)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)


def render(metrics: CurationMetrics) -> str:
    """Emit ``metrics`` as Prometheus exposition text (§16.11 named series).

    One line per series with ``# HELP`` / ``# TYPE`` headers; ``resolved_total`` fans
    out into one ``curation_tasks_resolved_total{task_type="…"}`` line per type,
    sorted for a deterministic scrape. A resolved histogram with no rows still emits a
    zero-valued ``{task_type=""}`` line so the series is always present.
    """
    lines: list[str] = []
    lines.append("# HELP curation_tasks_open Open curation backlog size.")
    lines.append("# TYPE curation_tasks_open gauge")
    lines.append(f"curation_tasks_open {_fmt(metrics.tasks_open)}")

    lines.append("# HELP curation_tasks_resolved_total Resolved curation tasks by type.")
    lines.append("# TYPE curation_tasks_resolved_total counter")
    resolved = metrics.resolved_total or {"": 0}
    for task_type, count in sorted(resolved.items()):
        lines.append(f'curation_tasks_resolved_total{{task_type="{task_type}"}} {_fmt(count)}')

    lines.append("# HELP verified_fields_protected_total Verified fields shielded from overwrite.")
    lines.append("# TYPE verified_fields_protected_total counter")
    lines.append(f"verified_fields_protected_total {_fmt(metrics.verified_fields_protected_total)}")

    lines.append("# HELP review_backlog_age_p95 p95 age (hours) of the open backlog.")
    lines.append("# TYPE review_backlog_age_p95 gauge")
    lines.append(f"review_backlog_age_p95 {_fmt(metrics.review_backlog_age_p95)}")

    lines.append("# HELP auto_resolved_ratio Share of resolutions closed automatically.")
    lines.append("# TYPE auto_resolved_ratio gauge")
    lines.append(f"auto_resolved_ratio {_fmt(metrics.auto_resolved_ratio)}")
    return "\n".join(lines) + "\n"
