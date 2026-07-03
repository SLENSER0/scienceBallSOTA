"""Cooling-rate conversion to canonical K/s (§7.2, reference table §7.8).

RU: Скорость охлаждения — это дельта температуры за единицу времени.
EN: A cooling rate is a temperature *delta* per unit time, so kelvin (K) and
degrees Celsius (degC) are magnitude-equal here — only the time unit scales.

Canonical target is ``K/s``. Supported units are ``{K/s, degC/s, K/min,
degC/min, K/h, degC/h}``. The §7.8 reference row ``60 degC/min → 1 K/s`` is a
direct consequence of the per-minute factor ``1/60``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Time-unit → seconds-per-unit scale toward the canonical per-second rate.
# per-second = 1, per-minute = 1/60, per-hour = 1/3600 (K and degC are equal).
_TIME_FACTORS: dict[str, float] = {
    "K/s": 1.0,
    "degC/s": 1.0,
    "K/min": 1.0 / 60.0,
    "degC/min": 1.0 / 60.0,
    "K/h": 1.0 / 3600.0,
    "degC/h": 1.0 / 3600.0,
}

COOLING_RATE_UNITS = tuple(_TIME_FACTORS)


@dataclass(frozen=True)
class CoolingRate:
    """A cooling rate carrying its canonical ``k_per_s`` magnitude (§7.2)."""

    value: float
    unit: str
    k_per_s: float
    method: str  # 'direct' (same unit) or 'converted'

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready mapping; ``k_per_s`` is the canonical K/s magnitude."""
        return {
            "value": self.value,
            "unit": self.unit,
            "k_per_s": self.k_per_s,
            "method": self.method,
        }


def to_k_per_s(value: float, unit: str) -> float:
    """Convert *value* in *unit* to the canonical cooling rate in ``K/s``.

    RU: Неизвестная единица — ошибка. EN: unknown units raise ``ValueError``.
    """
    if unit not in _TIME_FACTORS:
        raise ValueError(f"unsupported cooling-rate unit: {unit!r}")
    return value * _TIME_FACTORS[unit]


def convert_cooling_rate(value: float, from_unit: str, to_unit: str) -> CoolingRate:
    """Convert a cooling rate between units, carrying the K/s magnitude (§7.2).

    ``method`` is ``'direct'`` when *from_unit* equals *to_unit*, else
    ``'converted'``.
    """
    if from_unit not in _TIME_FACTORS:
        raise ValueError(f"unsupported cooling-rate unit: {from_unit!r}")
    if to_unit not in _TIME_FACTORS:
        raise ValueError(f"unsupported cooling-rate unit: {to_unit!r}")
    k_per_s = to_k_per_s(value, from_unit)
    if from_unit == to_unit:
        return CoolingRate(value=value, unit=to_unit, k_per_s=k_per_s, method="direct")
    out_value = k_per_s / _TIME_FACTORS[to_unit]
    return CoolingRate(value=out_value, unit=to_unit, k_per_s=k_per_s, method="converted")
