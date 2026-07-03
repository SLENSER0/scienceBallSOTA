"""Фильтр по типу/статусу пробелов для ``GET /gaps`` (§14.8).

Реализация фильтров эндпоинта ``GET /gaps`` из §14.8. Модуль на чистом stdlib:
константы допустимых типов пробелов (§11.1) и статусов, неизменяемый
:class:`GapFilter`, разбор query-параметров через :func:`parse_gap_filter`
и предикат :func:`matches` для отбора пробелов.

Type/status filters for the ``GET /gaps`` endpoint (§14.8). Pure stdlib:
constants for the allowed gap types (§11.1) and statuses, an immutable
:class:`GapFilter`, query parsing via :func:`parse_gap_filter`, and the
:func:`matches` predicate to test gap dicts.

* :data:`GAP_TYPES` — 9 допустимых типов пробелов §11.1 / 9 allowed gap types.
* :data:`GAP_STATUSES` — допустимые статусы пробела / allowed gap statuses.
* :class:`GapFilter` — неизменяемый фильтр с :meth:`as_dict`.
* :func:`parse_gap_filter` — типы/статус → ``GapFilter`` с валидацией.
* :func:`matches` — пробел + фильтр → ``bool``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Девять типов пробелов из §11.1 / the nine §11.1 gap types.
GAP_TYPES: frozenset[str] = frozenset(
    {
        "missing_property_value",
        "missing_baseline",
        "missing_processing_parameter",
        "missing_equipment",
        "missing_unit",
        "unverified_claim",
        "contradictory_measurements",
        "low_coverage_material",
        "orphan_entity",
    }
)

#: Допустимые статусы пробела §14.8 / allowed gap statuses (§14.8).
GAP_STATUSES: frozenset[str] = frozenset({"open", "known", "irrelevant"})


@dataclass(frozen=True, slots=True)
class GapFilter:
    """Неизменяемый фильтр ``GET /gaps`` по типу/статусу (§14.8).

    Immutable filter for the §14.8 ``GET /gaps`` query. ``types`` is a tuple of
    §11.1 gap types (empty tuple = match any type); ``status`` is one §14.8
    status or ``None`` (match any status). :meth:`as_dict` yields the wire form.
    """

    types: tuple[str, ...]
    status: str | None

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление фильтра / wire form (§14.8).

        ``types`` всегда список (возможно пустой); ``status`` включается только
        когда задан (не ``None``).
        """
        out: dict[str, Any] = {"types": list(self.types)}
        if self.status is not None:
            out["status"] = self.status
        return out


def parse_gap_filter(types: list[str] | None, status: str | None) -> GapFilter:
    """Разобрать параметры ``GET /gaps`` в :class:`GapFilter` (§14.8).

    Каждый элемент ``types`` обязан лежать в :data:`GAP_TYPES`; ``status`` —
    в :data:`GAP_STATUSES` либо ``None``. ``types`` ``None`` даёт пустой кортеж.

    Each ``types`` entry must be in :data:`GAP_TYPES`; ``status`` must be in
    :data:`GAP_STATUSES` or ``None``. ``types`` of ``None`` yields an empty tuple.

    :raises ValueError: если тип не входит в :data:`GAP_TYPES` или статус не
        входит в :data:`GAP_STATUSES` / when a type or status is not allowed.
    """
    if types is None:
        parsed_types: tuple[str, ...] = ()
    else:
        for t in types:
            if t not in GAP_TYPES:
                raise ValueError(f"unknown gap type: {t!r}")
        parsed_types = tuple(types)

    if status is not None and status not in GAP_STATUSES:
        raise ValueError(f"unknown gap status: {status!r}")

    return GapFilter(types=parsed_types, status=status)


def matches(gap: dict[str, Any], f: GapFilter) -> bool:
    """Проверить пробел против фильтра (§14.8).

    Test one gap dict against the filter. An empty ``f.types`` matches any type;
    otherwise ``gap['type']`` must be one of ``f.types``. ``f.status`` of
    ``None`` matches any status; otherwise ``gap['status']`` must equal it.
    Absent fields on ``gap`` fail the corresponding active filter.
    """
    if f.types and gap.get("type") not in f.types:
        return False
    return not (f.status is not None and gap.get("status") != f.status)
