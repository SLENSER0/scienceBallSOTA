"""SLA escalation tiers for review tasks (§16.4): эскалация по возрасту задачи.

:mod:`kg_common.storage.review_sla` reports only *overdue* (bool) and
:mod:`kg_common.storage.review_priority` a *base* priority — neither maps how far
past the SLA a task has aged onto an **escalation policy** (что делать, когда
задача просрочена сильнее). This module adds that policy: given the *overdue
ratio* ``age_hours / sla_hours`` it selects a tier, a priority bump and whether
the task should be reassigned to another curator.

Pure functions, no store, no ``datetime.now`` inside the logic — the caller
passes both the task's ``created_at`` and the current instant ``now`` as
ISO-8601 strings, so every result is deterministic and hand-checkable
(детерминированность: тот же вход даёт тот же тир).

Escalation tiers (тиры эскалации, по доле превышения ``overdue_ratio``)
----------------------------------------------------------------------
* ``none``      — ``ratio < 1.0``   : не просрочено, bump 0, без переназначения;
* ``warn``      — ``1.0 <= r < 1.5``: предупреждение, bump +1;
* ``breach``    — ``1.5 <= r < 3.0``: нарушение SLA, bump +3, переназначить
  **только если** задача никому не назначена (unassigned);
* ``critical``  — ``r >= 3.0``      : критично, bump +5, всегда переназначить.

RU/EN: эскалация / escalation, тир / tier, доля превышения / overdue ratio,
надбавка приоритета / priority bump, переназначение / reassign, назначено /
assigned, не назначено / unassigned, тип задачи / task type.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# -- tier vocabulary (словарь тиров, §16.4) -------------------------------
#: Допустимые значения ``Escalation.tier`` — от «нет эскалации» до «критично».
TIERS: frozenset[str] = frozenset({"none", "warn", "breach", "critical"})

# -- tier thresholds on overdue_ratio (пороги по доле превышения) ---------
WARN_RATIO: float = 1.0  # >= : SLA только что превышен (предупреждение)
BREACH_RATIO: float = 1.5  # >= : нарушение SLA (нужен пересмотр владельца)
CRITICAL_RATIO: float = 3.0  # >= : критично (переназначить безусловно)

# -- priority bump per tier (надбавка приоритета по тиру) -----------------
BUMP_BY_TIER: dict[str, int] = {"none": 0, "warn": 1, "breach": 3, "critical": 5}

# Fallback SLA, если task_type не найден в sla_map (см. :func:`escalate_queue`).
FALLBACK_SLA_HOURS: float = 48.0


@dataclass(frozen=True)
class Escalation:
    """Решение об эскалации по одной задаче ревью — escalation decision (§16.4).

    Fields
    ------
    task_id:
        Идентификатор задачи ревью (``task_id``).
    tier:
        Тир эскалации — один из :data:`TIERS`
        (``none`` / ``warn`` / ``breach`` / ``critical``).
    priority_bump:
        Надбавка к базовому приоритету (0 / +1 / +3 / +5) — см. :data:`BUMP_BY_TIER`.
    reassign:
        Нужно ли переназначить задачу другому куратору (переназначение).
    """

    task_id: str
    tier: str
    priority_bump: int
    reassign: bool

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict для JSON/логов — flat dict for serialization."""
        return {
            "task_id": self.task_id,
            "tier": self.tier,
            "priority_bump": self.priority_bump,
            "reassign": self.reassign,
        }


def _parse_iso(value: str) -> datetime:
    """ISO-8601 timestamp → aware ``datetime`` (терпим суффикс ``Z``; naive → UTC)."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _is_unassigned(task: Mapping[str, Any]) -> bool:
    """Задача никому не назначена — пустой/отсутствующий ``assignee``."""
    return not str(task.get("assignee", "")).strip()


def escalate(task: Mapping[str, Any], now: str, sla_hours: float) -> Escalation:
    """Оценить эскалацию задачи по ``overdue_ratio = age_hours / sla_hours`` (§16.4).

    ``age_hours = (now - task['created_at']) / 1h``. При ``sla_hours <= 0`` доля
    превышения принимается 0.0 (защита от деления на ноль → тир ``none``).

    Отображение доли превышения на тир — см. модульный docstring:
    ``<1.0`` → ``none``(bump 0); ``1.0..1.5`` → ``warn``(+1); ``1.5..3.0`` →
    ``breach``(+3, reassign только если задача не назначена); ``>=3.0`` →
    ``critical``(+5, reassign всегда).
    """
    task_id = str(task.get("task_id", ""))
    created = _parse_iso(str(task["created_at"]))
    now_dt = _parse_iso(now)
    age_hours = (now_dt - created).total_seconds() / 3600.0
    overdue_ratio = age_hours / sla_hours if sla_hours > 0 else 0.0

    if overdue_ratio >= CRITICAL_RATIO:
        tier, reassign = "critical", True
    elif overdue_ratio >= BREACH_RATIO:
        tier, reassign = "breach", _is_unassigned(task)
    elif overdue_ratio >= WARN_RATIO:
        tier, reassign = "warn", False
    else:
        tier, reassign = "none", False

    return Escalation(
        task_id=task_id,
        tier=tier,
        priority_bump=BUMP_BY_TIER[tier],
        reassign=reassign,
    )


def escalate_queue(
    tasks: Iterable[Mapping[str, Any]],
    now: str,
    sla_map: Mapping[str, float],
) -> list[Escalation]:
    """Проэскалировать очередь задач, беря SLA по ``task_type`` из ``sla_map`` (§16.4).

    Для каждой задачи срок берётся как ``sla_map[task['task_type']]`` с падением
    на :data:`FALLBACK_SLA_HOURS`, когда тип не найден. Порядок результата
    совпадает с порядком ``tasks`` (детерминированность).
    """
    result: list[Escalation] = []
    for task in tasks:
        task_type = str(task.get("task_type", ""))
        sla_hours = float(sla_map.get(task_type, FALLBACK_SLA_HOURS))
        result.append(escalate(task, now, sla_hours))
    return result
