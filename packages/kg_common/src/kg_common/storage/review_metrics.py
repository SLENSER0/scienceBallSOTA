"""Review-queue throughput + aging metrics (§16.11 метрики очереди ревью).

Pure functions over *task rows* — no store, no I/O, no ``datetime.now`` inside the
logic. Every instant the metrics need (the current moment ``now``, a window start
``since``) is passed in by the caller as an ISO-8601 string, so the numbers are
fully deterministic and hand-checkable (детерминированность). The row shape
mirrors :class:`kg_common.storage.review_queue.ReviewTask` as a plain dict::

    {"status": "open" | "in_review" | "resolved",   # жизненный цикл задачи
     "kind": "low_confidence",                        # вид задачи (для by_kind)
     "created_at": "2026-01-01T00:00:00",             # ISO-8601, момент постановки
     "resolved_at": "2026-01-02T00:00:00",            # ISO-8601, present when resolved
     "sla_hours": 24.0}                               # optional per-task SLA

This module *reads* that shape; it never touches the queue store. The time math is
reused from :mod:`kg_common.storage.review_priority` (:func:`age_hours` /
:func:`is_overdue`) so aging is defined identically across §16.4/§16.11.

What "aging" measures (что считается старением)
-----------------------------------------------
The aging signals — ``avg_age_hours``, ``oldest_age_hours`` and ``overdue`` — are
computed over the **open backlog** (rows with ``status == "open"``): work still
waiting for a curator to pick up. Once a task is ``in_review`` a reviewer owns it,
and once ``resolved`` it has left the queue, so neither ages further here. The age
of an open task is the wall-clock gap from its ``created_at`` to ``now``.
:func:`backlog_trend` likewise tracks the *open* count over time; ``total`` and
``by_kind`` describe the whole queue, and :func:`throughput` counts resolutions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from kg_common.storage.review_priority import age_hours, is_overdue

# -- task lifecycle statuses (mirror kg_common.storage.review_queue, §16.4) --
STATUS_OPEN = "open"
STATUS_IN_REVIEW = "in_review"
STATUS_RESOLVED = "resolved"

# -- backlog-trend verdicts (вердикт тренда бэклога, §16.11) ---------------
TREND_IMPROVING = "improving"  # open-count упал: очередь разгружается
TREND_WORSENING = "worsening"  # open-count вырос: очередь копится
TREND_STABLE = "stable"  # без изменений либо недостаточно точек

_AGE_PRECISION = 6  # округление часов возраста (гасим шум float в отображении)


@dataclass(frozen=True)
class QueueMetrics:
    """Snapshot of review-queue health — снимок состояния очереди (§16.11).

    Fields
    ------
    total:
        Every row seen (весь размер очереди).
    open / in_review / resolved:
        Per-status counts (счётчики по статусу).
    overdue:
        Open tasks whose age has passed their ``sla_hours`` (просрочка SLA); rows
        without an ``sla_hours`` can never be overdue.
    avg_age_hours / oldest_age_hours:
        Mean / max age of the open backlog measured from ``now`` (средний /
        максимальный возраст открытых задач); ``0.0`` when the backlog is empty.
    by_kind:
        ``{kind: count}`` histogram over **all** rows (гистограмма по видам),
        sorted by kind for a deterministic view.
    """

    total: int
    open: int
    in_review: int
    resolved: int
    overdue: int
    avg_age_hours: float
    oldest_age_hours: float
    by_kind: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (all fields, JSON-friendly, ``by_kind`` copied)."""
        return asdict(self)


def queue_metrics(tasks: Sequence[Mapping[str, Any]], *, now: str) -> QueueMetrics:
    """Aggregate ``tasks`` into a :class:`QueueMetrics` as of ``now`` (§16.11).

    ``now`` is an explicit ISO-8601 instant (детерминированность — no wall clock is
    read here). Aging (``avg_age_hours`` / ``oldest_age_hours`` / ``overdue``) is
    over the open backlog; ``by_kind`` is over every row. Rows with an unknown
    ``status`` still count toward ``total`` and ``by_kind`` but no status bucket.
    See the module docstring for the row shape.
    """
    open_count = in_review = resolved = overdue = 0
    by_kind: dict[str, int] = {}
    open_ages: list[float] = []
    for task in tasks:
        status = task.get("status", "")
        kind = str(task.get("kind", ""))
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if status == STATUS_IN_REVIEW:
            in_review += 1
            continue
        if status == STATUS_RESOLVED:
            resolved += 1
            continue
        if status == STATUS_OPEN:
            open_count += 1
            created_at = task.get("created_at")
            if not created_at:
                continue
            open_ages.append(age_hours(str(created_at), now))
            sla_hours = task.get("sla_hours")
            if sla_hours is not None and is_overdue(str(created_at), now, sla_hours):
                overdue += 1
    avg_age = round(sum(open_ages) / len(open_ages), _AGE_PRECISION) if open_ages else 0.0
    oldest_age = round(max(open_ages), _AGE_PRECISION) if open_ages else 0.0
    return QueueMetrics(
        total=len(tasks),
        open=open_count,
        in_review=in_review,
        resolved=resolved,
        overdue=overdue,
        avg_age_hours=avg_age,
        oldest_age_hours=oldest_age,
        by_kind=dict(sorted(by_kind.items())),
    )


def throughput(tasks: Sequence[Mapping[str, Any]], *, since: str, now: str) -> int:
    """Count tasks resolved within the window ``[since, now]`` (пропускная способность).

    A row counts when its ``status`` is ``resolved`` and its ``resolved_at`` ISO
    stamp falls inside the inclusive window ``since <= resolved_at <= now``. Rows
    that are not resolved, or resolved without a ``resolved_at``, are ignored. Both
    bounds are inclusive; ``since`` and ``now`` are explicit ISO-8601 instants.
    """
    count = 0
    for task in tasks:
        if task.get("status") != STATUS_RESOLVED:
            continue
        resolved_at = task.get("resolved_at")
        if not resolved_at:
            continue
        stamp = str(resolved_at)
        if age_hours(since, stamp) >= 0.0 and age_hours(stamp, now) >= 0.0:
            count += 1
    return count


def _open_count(snapshot: Any) -> int:
    """Extract the open-task count from a snapshot (QueueMetrics / mapping / int)."""
    if isinstance(snapshot, QueueMetrics):
        return snapshot.open
    if isinstance(snapshot, Mapping):
        return int(snapshot["open"])
    return int(snapshot)


def backlog_trend(snapshots: Sequence[Any]) -> str:
    """Classify the open-backlog trend over ordered ``snapshots`` (§16.11).

    Compares the open count of the **first** snapshot to the **last**: a smaller
    final backlog is :data:`TREND_IMPROVING`, a larger one :data:`TREND_WORSENING`,
    and an equal one (or fewer than two snapshots) :data:`TREND_STABLE`. Each
    snapshot may be a :class:`QueueMetrics`, a mapping with an ``"open"`` key (e.g.
    :meth:`QueueMetrics.as_dict`), or a plain open-count int.
    """
    if len(snapshots) < 2:
        return TREND_STABLE
    first = _open_count(snapshots[0])
    last = _open_count(snapshots[-1])
    if last < first:
        return TREND_IMPROVING
    if last > first:
        return TREND_WORSENING
    return TREND_STABLE
