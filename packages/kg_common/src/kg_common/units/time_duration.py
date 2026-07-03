"""Time/duration conversion to canonical hours (``h``) and seconds (§7.2/§8).

RU: Длительность приводится к каноническим единицам — часам (``time_h``) и
секундам. Поддерживаются s/sec, ms, min, h/hr/hour, day, week.
EN: A duration is normalised to canonical hours (``time_h``) and seconds.
Every supported unit maps to a fixed number of seconds, from which hours follow
via ``/ 3600``. The §7.2 row ``1 day → 24 h`` and ``1 day → 86400 s`` are direct
consequences of ``day = 24 h`` and ``h = 3600 s``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_SECONDS_PER_HOUR = 3600.0

# Canonical seconds-per-unit factors toward the base unit (second).
# ms = 1e-3 s, min = 60 s, h = 3600 s, day = 24 h, week = 168 h.
_SECONDS_PER_UNIT: dict[str, float] = {
    "s": 1.0,
    "sec": 1.0,
    "ms": 1e-3,
    "min": 60.0,
    "h": _SECONDS_PER_HOUR,
    "hr": _SECONDS_PER_HOUR,
    "hour": _SECONDS_PER_HOUR,
    "day": 24.0 * _SECONDS_PER_HOUR,
    "week": 168.0 * _SECONDS_PER_HOUR,
}

DURATION_UNITS = tuple(_SECONDS_PER_UNIT)


class UnknownDurationUnitError(ValueError):
    """Duration unit symbol is not supported — неизвестная единица (§7.2)."""

    def __init__(self, unit: str) -> None:
        self.unit = unit
        super().__init__(f"unknown duration unit: {unit!r}")


@dataclass(frozen=True)
class Duration:
    """A duration carrying its canonical ``hours`` and ``seconds`` magnitudes (§7.2)."""

    value_raw: float
    from_unit: str
    hours: float
    seconds: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready mapping; ``hours``/``seconds`` are canonical magnitudes."""
        return {
            "value_raw": self.value_raw,
            "from_unit": self.from_unit,
            "hours": self.hours,
            "seconds": self.seconds,
        }


def to_seconds(value: float, unit: str) -> float:
    """Convert *value* in *unit* to canonical seconds (§7.2).

    RU: Неизвестная единица — ошибка. EN: unknown units raise
    :class:`UnknownDurationUnitError`.
    """
    if unit not in _SECONDS_PER_UNIT:
        raise UnknownDurationUnitError(unit)
    return value * _SECONDS_PER_UNIT[unit]


def to_hours(value: float, unit: str) -> float:
    """Convert *value* in *unit* to canonical hours (``time_h``, §7.2)."""
    return to_seconds(value, unit) / _SECONDS_PER_HOUR


def convert_duration(value: float, from_unit: str, to_unit: str) -> Duration:
    """Convert a duration, carrying canonical hours and seconds (§7.2).

    RU: *to_unit* валидируется, но каноническими остаются часы и секунды.
    EN: *to_unit* is validated (so unknown targets raise), while the returned
    :class:`Duration` always exposes canonical ``hours`` and ``seconds``.
    """
    if to_unit not in _SECONDS_PER_UNIT:
        raise UnknownDurationUnitError(to_unit)
    seconds = to_seconds(value, from_unit)
    return Duration(
        value_raw=value,
        from_unit=from_unit,
        hours=seconds / _SECONDS_PER_HOUR,
        seconds=seconds,
    )
