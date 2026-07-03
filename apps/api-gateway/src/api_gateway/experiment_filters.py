"""Фильтры списка экспериментов для ``GET /experiments`` (§14.8).

Полный набор фильтров эндпоинта ``GET /experiments`` из §14.8, отдельный от
меньшей модели ``SearchFilters`` в search-роутере. Модуль на чистом stdlib:
разбор query-параметров в неизменяемый :class:`ExperimentFilters`, сериализация
через :meth:`ExperimentFilters.as_dict` (пропускает ``None``) и предикат
:func:`matches` для отбора строк-экспериментов.

Full filter set for the ``GET /experiments`` endpoint (§14.8), distinct from the
smaller ``SearchFilters`` model in the search router. Pure stdlib: parse query
params into an immutable :class:`ExperimentFilters`, serialise via
:meth:`ExperimentFilters.as_dict` (omitting ``None`` fields), and test rows with
:func:`matches`.

* :class:`ExperimentFilters` — frozen filter set with :meth:`as_dict`.
* :func:`parse_experiment_filters` — query mapping → ``ExperimentFilters``.
* :func:`matches` — experiment dict + filters → ``bool``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class ExperimentFilters:
    """Неизменяемый набор фильтров ``GET /experiments`` (§14.8).

    Immutable filter set encoding the §14.8 ``GET /experiments`` query. Every
    field is optional except ``verified_only`` which defaults to ``False``.
    :meth:`as_dict` yields the wire form with ``None`` fields omitted so the set
    of *active* filters is explicit.
    """

    material: str | None = None
    operation: str | None = None
    temperature_c: float | None = None
    time_h: float | None = None
    atmosphere: str | None = None
    equipment: str | None = None
    property: str | None = None
    regime: str | None = None
    date_from: str | None = None
    min_confidence: float | None = None
    verified_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление только активных фильтров (§14.8).

        Пропускает ``None``-поля; булев ``verified_only`` включается только когда
        ``True`` (значение по умолчанию ``False`` считается неактивным), поэтому
        словарь содержит ровно набор *заданных* фильтров.

        Emits only active filters: ``None`` fields are omitted and the boolean
        ``verified_only`` appears only when ``True`` (its ``False`` default counts
        as inactive), so the dict is exactly the set of *set* filters.
        """
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            if f.name == "verified_only" and value is False:
                continue
            out[f.name] = value
        return out


def _coerce_float(params: Mapping[str, Any], key: str) -> float | None:
    """Привести параметр к ``float`` или ``None`` / coerce to float (§14.8)."""
    if key not in params or params[key] is None:
        return None
    return float(params[key])


def parse_experiment_filters(params: Mapping[str, Any]) -> ExperimentFilters:
    """Разобрать query-параметры в :class:`ExperimentFilters` (§14.8).

    ``temperature_c`` и ``time_h`` приводятся к ``float``; ``min_confidence``
    обязан лежать в ``[0, 1]``; ``verified_only`` трактуется как булев флаг.

    ``temperature_c`` and ``time_h`` are coerced to ``float``. ``min_confidence``
    must lie within ``[0, 1]``. ``verified_only`` is read as a boolean flag.

    :raises ValueError: если ``min_confidence`` вне диапазона ``[0, 1]`` /
        when ``min_confidence`` is outside ``[0, 1]``.
    """
    min_confidence = _coerce_float(params, "min_confidence")
    if min_confidence is not None and not (0.0 <= min_confidence <= 1.0):
        raise ValueError(f"min_confidence must be in [0, 1], got {min_confidence!r}")

    return ExperimentFilters(
        material=params.get("material"),
        operation=params.get("operation"),
        temperature_c=_coerce_float(params, "temperature_c"),
        time_h=_coerce_float(params, "time_h"),
        atmosphere=params.get("atmosphere"),
        equipment=params.get("equipment"),
        property=params.get("property"),
        regime=params.get("regime"),
        date_from=params.get("date_from"),
        min_confidence=min_confidence,
        verified_only=bool(params.get("verified_only", False)),
    )


def matches(exp: dict[str, Any], f: ExperimentFilters) -> bool:
    """Проверить эксперимент против фильтров (§14.8).

    Test one experiment dict against the active filters. ``material``/
    ``operation`` compare case-insensitively for equality; ``confidence`` must be
    at least ``min_confidence``; ``verified_only`` requires ``exp['verified']``;
    ``date_from`` must be ``<=`` ``exp['date']`` by lexicographic ISO comparison.
    Absent fields on ``exp`` fail the corresponding active filter.
    """
    if f.material is not None and str(exp.get("material", "")).lower() != f.material.lower():
        return False
    if f.operation is not None and str(exp.get("operation", "")).lower() != f.operation.lower():
        return False
    if f.min_confidence is not None:
        conf = exp.get("confidence")
        if not isinstance(conf, (int, float)) or conf < f.min_confidence:
            return False
    if f.verified_only and exp.get("verified") is not True:
        return False
    if f.date_from is not None:
        date = exp.get("date")
        if not isinstance(date, str) or f.date_from > date:
            return False
    return True
