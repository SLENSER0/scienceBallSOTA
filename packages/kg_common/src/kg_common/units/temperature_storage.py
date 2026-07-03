"""Dual temperature storage — degC display + kelvin internal (§7.2).

RU: Политика §7.2 требует хранить температуру одновременно в градусах Цельсия
    (для отображения) и в кельвинах (внутреннее каноническое хранение).
EN: §7.2 mandates keeping temperature in both degC (display) and kelvin
    (internal storage). This module produces that dual record from any accepted
    input unit and flags physically impossible values below absolute zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 0 degC in kelvin — the Celsius/Kelvin offset (0 K is absolute zero).
_KELVIN_OFFSET: float = 273.15


class UnknownTemperatureUnitError(ValueError):
    """Raised for an unrecognised temperature unit — неизвестная единица."""


# Accepted spellings grouped by canonical scale (case-insensitive lookup).
_CELSIUS_UNITS: frozenset[str] = frozenset({"degc", "c", "°c"})
_KELVIN_UNITS: frozenset[str] = frozenset({"k", "kelvin"})
_FAHRENHEIT_UNITS: frozenset[str] = frozenset({"degf", "f", "°f"})


@dataclass(frozen=True)
class TemperatureStorage:
    """A dual temperature record — raw input plus degC and kelvin (§7.2)."""

    value_raw: float
    from_unit: str
    deg_c: float
    kelvin: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready mapping carrying both display and internal magnitudes."""
        return {
            "value_raw": self.value_raw,
            "from_unit": self.from_unit,
            "deg_c": self.deg_c,
            "kelvin": self.kelvin,
        }


def _to_celsius(value: float, unit_key: str) -> float:
    """Convert *value* to degC given a normalised *unit_key* (§7.2)."""
    if unit_key in _CELSIUS_UNITS:
        return value
    if unit_key in _KELVIN_UNITS:
        return value - _KELVIN_OFFSET
    if unit_key in _FAHRENHEIT_UNITS:
        return (value - 32.0) * 5.0 / 9.0
    raise UnknownTemperatureUnitError(f"unknown temperature unit: {unit_key!r}")


def to_storage(value: float, unit: str) -> TemperatureStorage:
    """Build a dual degC/kelvin :class:`TemperatureStorage` from any input.

    RU: Принимает degC/C/°C, K/kelvin, degF/F/°F; иначе — ошибка.
    EN: Accepts degC/C/°C, K/kelvin, degF/F/°F; anything else raises
    :class:`UnknownTemperatureUnitError`.
    """
    unit_key = unit.strip().lower()
    if unit_key not in (_CELSIUS_UNITS | _KELVIN_UNITS | _FAHRENHEIT_UNITS):
        raise UnknownTemperatureUnitError(f"unknown temperature unit: {unit!r}")
    deg_c = _to_celsius(value, unit_key)
    kelvin = deg_c + _KELVIN_OFFSET
    return TemperatureStorage(value_raw=value, from_unit=unit, deg_c=deg_c, kelvin=kelvin)


def below_absolute_zero(ts: TemperatureStorage) -> bool:
    """True when *ts* sits below absolute zero — физически невозможно (K < 0)."""
    return ts.kelvin < 0.0
