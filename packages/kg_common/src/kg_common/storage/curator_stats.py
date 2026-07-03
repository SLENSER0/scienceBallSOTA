"""Per-curator productivity stats for the admin panel (§16.11 статистика кураторов).

:mod:`kg_common.storage.review_metrics` answers *aggregate* throughput — how many
tasks the queue as a whole resolves. §16.11's admin panel additionally needs the
work broken down **per curator** (по каждому куратору): who resolved how much, what
their action-mix looks like, and how long their resolutions take. This module adds
that per-actor cut as pure functions over two plain-dict row shapes; it reads no
store and no wall clock, so every number is deterministic and hand-checkable.

Row shapes (формы строк)
------------------------
A *curation event* — one action a curator took (mirrors the §16.9 activity feed)::

    {"event_id": "e1",           # уникальный id события
     "actor_id": "alice",        # кто выполнил действие (curator / куратор)
     "action": "accept"}         # вид действия (accept / dismiss / merge / ...)

A *review task* — one queued item (mirrors §16.4 ``ReviewTask``)::

    {"status": "resolved",           # жизненный цикл: open / in_review / resolved / dismissed
     "assignee": "alice",            # назначенный куратор (used for the dismissed count)
     "created_at": "2026-01-01T00:00:00",   # ISO-8601, когда задача поставлена
     "resolved_at": "2026-01-01T02:00:00",  # ISO-8601, когда закрыта (present when resolved)
     "resolved_by_event_id": "e1"}          # event_id закрывшего действия -> resolver

The resolver of a task is found by joining ``resolved_by_event_id`` to the matching
event's ``actor_id`` (событие-«закрытие» указывает на куратора). Resolution latency
reuses :func:`kg_common.storage.review_priority.age_hours`, so the hours math is
defined identically across §16.4/§16.11.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from kg_common.storage.review_priority import age_hours

STATUS_RESOLVED = "resolved"  # задача закрыта (mirror §16.4 review_queue)
STATUS_DISMISSED = "dismissed"  # задача отклонена без изменения графа

_HOURS_PRECISION = 6  # округление часов резолюции (гасим шум float в отображении)


@dataclass(frozen=True)
class CuratorStat:
    """Productivity snapshot for one curator — снимок продуктивности куратора (§16.11).

    Fields
    ------
    actor_id:
        The curator's id (идентификатор куратора).
    resolved:
        Tasks this curator resolved (задачи, закрытые куратором) — counted via the
        ``resolved_by_event_id`` -> event ``actor_id`` join.
    dismissed:
        Tasks with status ``dismissed`` whose ``assignee`` is this curator
        (отклонённые задачи куратора).
    action_counts:
        ``{action: count}`` histogram over the curator's events (гистограмма
        действий: accept / dismiss / merge / ...), sorted by action.
    avg_resolution_hours:
        Mean wall-clock hours from ``created_at`` to ``resolved_at`` over the tasks
        this curator resolved (средняя длительность резолюции); ``0.0`` when the
        curator resolved nothing.
    """

    actor_id: str
    resolved: int
    dismissed: int
    action_counts: dict[str, int] = field(default_factory=dict)
    avg_resolution_hours: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для admin-панели / API); ``action_counts`` копируется."""
        return asdict(self)


def compute_stats(
    events: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
) -> list[CuratorStat]:
    """Aggregate ``events`` + ``tasks`` into one :class:`CuratorStat` per curator (§16.11).

    ``action_counts`` is grouped from ``events`` by ``actor_id``. ``resolved`` and
    ``avg_resolution_hours`` come from ``tasks`` with status ``resolved``: each such
    task is attributed to the curator whose event ``event_id`` matches the task's
    ``resolved_by_event_id`` (so the resolver, not the assignee, gets the credit),
    and its latency is :func:`age_hours` from ``created_at`` to ``resolved_at``.
    ``dismissed`` counts tasks with status ``dismissed`` by ``assignee``.

    Every actor seen in any of these roles gets exactly one row; rows are sorted by
    ``actor_id`` for a deterministic view.
    """
    event_actor: dict[str, str] = {}  # event_id -> actor_id (для join задача->куратор)
    action_counts: dict[str, dict[str, int]] = {}  # actor_id -> {action: count}
    for event in events:
        actor_id = str(event.get("actor_id", ""))
        event_id = event.get("event_id")
        if event_id is not None:
            event_actor[str(event_id)] = actor_id
        action = str(event.get("action", ""))
        action_counts.setdefault(actor_id, {})
        action_counts[actor_id][action] = action_counts[actor_id].get(action, 0) + 1

    resolved_count: dict[str, int] = {}  # actor_id -> число закрытых задач
    resolution_hours: dict[str, list[float]] = {}  # actor_id -> длительности резолюций
    dismissed_count: dict[str, int] = {}  # actor_id -> число отклонённых задач
    for task in tasks:
        status = task.get("status")
        if status == STATUS_RESOLVED:
            resolver = event_actor.get(str(task.get("resolved_by_event_id", "")))
            if resolver is None:
                continue  # закрытие без известного события -> некому приписать
            resolved_count[resolver] = resolved_count.get(resolver, 0) + 1
            created_at = task.get("created_at")
            resolved_at = task.get("resolved_at")
            if created_at and resolved_at:
                resolution_hours.setdefault(resolver, []).append(
                    age_hours(str(created_at), str(resolved_at))
                )
        elif status == STATUS_DISMISSED:
            assignee = str(task.get("assignee", ""))
            dismissed_count[assignee] = dismissed_count.get(assignee, 0) + 1

    actors = set(action_counts) | set(resolved_count) | set(dismissed_count)
    stats: list[CuratorStat] = []
    for actor_id in sorted(actors):
        hours = resolution_hours.get(actor_id, [])
        avg_hours = round(sum(hours) / len(hours), _HOURS_PRECISION) if hours else 0.0
        stats.append(
            CuratorStat(
                actor_id=actor_id,
                resolved=resolved_count.get(actor_id, 0),
                dismissed=dismissed_count.get(actor_id, 0),
                action_counts=dict(sorted(action_counts.get(actor_id, {}).items())),
                avg_resolution_hours=avg_hours,
            )
        )
    return stats


def leaderboard(stats: Sequence[CuratorStat]) -> list[str]:
    """Rank curators by resolved count — таблица лидеров (§16.11).

    Returns ``actor_id`` values sorted by ``resolved`` **descending**, ties broken by
    ``actor_id`` **ascending** (детерминированный порядок при равном числе задач).
    """
    ordered = sorted(stats, key=lambda s: (-s.resolved, s.actor_id))
    return [s.actor_id for s in ordered]
