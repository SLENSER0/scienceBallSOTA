"""SLA/aging config per ``task_type`` (§16.4): срок реакции на задачи ревью.

Pure functions over *review-task metadata* — no store, no I/O beyond parsing ISO
timestamps (детерминированность: тот же вход даёт тот же статус). Каждый тип задачи
(``task_type``) имеет свой SLA в часах — как быстро курация должна отреагировать::

    contradiction         →   4 h   # противоречие: срочно
    missing_critical_field →  12 h
    ambiguous_er          →  24 h
    low_confidence        →  48 h
    low_quality_ocr       →  72 h
    new_schema_term       →  168 h  # неделя

:func:`sla_for` разрешает срок с учётом переопределений (overrides), падая на
дефолт, а затем на общий fallback 48 h. :func:`evaluate` считает возраст задачи в
часах и её просроченность (overdue), возвращая замороженный :class:`SlaStatus`.
RU/EN: срок / SLA, возраст / age, просрочено / overdue, доля превышения /
breach ratio, тип задачи / task type.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Дефолтный fallback, когда task_type не найден ни в overrides, ни в defaults.
FALLBACK_SLA_HOURS: float = 48.0

# Дефолтные сроки реакции по типу задачи ревью (в часах) — §16.4.
DEFAULT_SLA_HOURS: dict[str, float] = {
    "contradiction": 4.0,
    "missing_critical_field": 12.0,
    "ambiguous_er": 24.0,
    "low_confidence": 48.0,
    "low_quality_ocr": 72.0,
    "new_schema_term": 168.0,
}


@dataclass(frozen=True)
class SlaStatus:
    """Статус SLA по одной задаче ревью — snapshot over review-task age (§16.4).

    Fields
    ------
    task_type:
        Тип задачи (ключ в :data:`DEFAULT_SLA_HOURS`).
    age_hours:
        Возраст задачи в часах = (now - created_at) / 1h.
    sla_hours:
        Разрешённый срок реакции (см. :func:`sla_for`).
    overdue:
        Просрочено ли — ``True``, когда ``age_hours >= sla_hours``.
    breach_ratio:
        Доля превышения = ``age_hours / sla_hours`` (>= 1.0 при просрочке).
    """

    task_type: str
    age_hours: float
    sla_hours: float
    overdue: bool
    breach_ratio: float

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict для JSON/логов — flat dict for serialization."""
        return {
            "task_type": self.task_type,
            "age_hours": self.age_hours,
            "sla_hours": self.sla_hours,
            "overdue": self.overdue,
            "breach_ratio": self.breach_ratio,
        }


def sla_for(task_type: str, overrides: Mapping[str, float] | None = None) -> float:
    """Разрешить срок SLA для ``task_type`` — override → default → fallback.

    Порядок: если ``task_type`` есть в ``overrides`` — берём его; иначе дефолт из
    :data:`DEFAULT_SLA_HOURS`; иначе общий :data:`FALLBACK_SLA_HOURS` (48 h).
    """
    if overrides is not None and task_type in overrides:
        return float(overrides[task_type])
    if task_type in DEFAULT_SLA_HOURS:
        return DEFAULT_SLA_HOURS[task_type]
    return FALLBACK_SLA_HOURS


def _parse_iso(value: str) -> datetime:
    """Разобрать ISO-8601 timestamp (терпим суффикс ``Z``) → aware ``datetime``."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def evaluate(
    task_type: str,
    created_at_iso: str,
    now_iso: str,
    overrides: Mapping[str, float] | None = None,
) -> SlaStatus:
    """Оценить SLA задачи: возраст, просрочка, доля превышения — §16.4.

    ``age_hours = (now - created_at) / 1h``; ``overdue`` при ``age >= sla``;
    ``breach_ratio = age / sla`` (защита от деления на ноль: sla<=0 → ratio 0.0).
    """
    created = _parse_iso(created_at_iso)
    now = _parse_iso(now_iso)
    sla_hours = sla_for(task_type, overrides)
    age_hours = (now - created).total_seconds() / 3600.0
    overdue = age_hours >= sla_hours
    breach_ratio = age_hours / sla_hours if sla_hours > 0 else 0.0
    return SlaStatus(
        task_type=task_type,
        age_hours=age_hours,
        sla_hours=sla_hours,
        overdue=overdue,
        breach_ratio=breach_ratio,
    )
