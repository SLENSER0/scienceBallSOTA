"""Canonical stress/strength unit conversion — прочность/напряжение (§7.2).

The general-purpose registry in :mod:`kg_common.units.conversions` carries a
*pressure* dimension (``MPa`` / ``bar`` / ``atm`` / ``psi`` / ``kPa``) tuned for
process pressures, but §7.2's canonical target unit for a **strength/stress
class** is ``MPa`` and the material-science inputs it must accept are broader:
``GPa`` (tensile moduli, ГПа), ``ksi`` / ``psi`` (imperial datasheets),
``N/mm2`` (an exact synonym of ``MPa``) and ``kgf/mm2`` (legacy hardness-derived
strength tables). This module is the dedicated §7.2 converter to canonical MPa.

Каноническая целевая единица класса прочности/напряжения — ``MPa``.

Public API:

* :class:`StressConversion` — frozen record of one conversion, with ``as_dict``.
* :func:`to_mpa`            — value in a stress unit → megapascals (canonical).
* :func:`convert_stress`    — value between two stress units, as a record.
* :class:`UnknownStressUnitError` — raised on an unrecognised unit symbol.

Pure Python, no I/O. Unit strings match after stripping surrounding whitespace;
``N/mm2`` accepts the ``N/mm^2`` and ``N/mm²`` spellings, ``kgf/mm2`` likewise.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Canonical target unit and the MPa-per-unit scale factors (§7.2).
#
#   1 MPa      = 1 MPa            (canonical / identity)
#   1 GPa      = 1000 MPa
#   1 kPa      = 1e-3 MPa
#   1 Pa       = 1e-6 MPa
#   1 ksi      = 6.894757 MPa     (1000·psi, exact-to-6dp datasheet constant)
#   1 psi      = 6.894757e-3 MPa
#   1 N/mm2    = 1 MPa            (exact synonym)
#   1 kgf/mm2  = 9.80665 MPa      (g0 = 9.80665 m/s², exact)
# ---------------------------------------------------------------------------
CANONICAL: str = "MPa"

_KSI_MPA = 6.894757
_KGF_MM2_MPA = 9.80665

_MPA_PER_UNIT: dict[str, float] = {
    "MPa": 1.0,
    "GPa": 1000.0,
    "kPa": 1.0e-3,
    "Pa": 1.0e-6,
    "ksi": _KSI_MPA,
    "psi": _KSI_MPA * 1.0e-3,
    "N/mm2": 1.0,
    "kgf/mm2": _KGF_MM2_MPA,
}

# Spelling aliases folded onto the canonical keys above — синонимы написания.
_ALIASES: dict[str, str] = {
    "N/mm^2": "N/mm2",
    "N/mm²": "N/mm2",
    "kgf/mm^2": "kgf/mm2",
    "kgf/mm²": "kgf/mm2",
}


class UnknownStressUnitError(ValueError):
    """Stress unit symbol is not recognised — неизвестная единица (§7.2)."""

    def __init__(self, unit: str) -> None:
        self.unit = unit
        super().__init__(f"unknown stress unit: {unit!r}")


@dataclass(frozen=True, slots=True)
class StressConversion:
    """One stress/strength conversion to canonical MPa — запись конвертации.

    Attributes:
        value_raw: the input magnitude, in ``from_unit``.
        from_unit: the source unit symbol (as resolved, canonical spelling).
        value_mpa: ``value_raw`` expressed in megapascals.
        target:    the canonical target unit — always ``"MPa"`` for §7.2.
    """

    value_raw: float
    from_unit: str
    value_mpa: float
    target: str = CANONICAL

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-``dict`` view — сериализуемое представление."""
        return asdict(self)


def _resolve(unit: str) -> str:
    """Fold ``unit`` onto a canonical registry key or raise — разбор единицы."""
    key = unit.strip()
    key = _ALIASES.get(key, key)
    if key not in _MPA_PER_UNIT:
        raise UnknownStressUnitError(unit)
    return key


def to_mpa(value: float, unit: str) -> float:
    """Convert ``value`` in ``unit`` to megapascals — перевод в МПа (§7.2).

    Raises:
        UnknownStressUnitError: if ``unit`` is not a known stress unit.
    """
    return value * _MPA_PER_UNIT[_resolve(unit)]


def convert_stress(value: float, from_unit: str, to_unit: str) -> StressConversion:
    """Convert ``value`` between stress units — конвертация напряжения (§7.2).

    ``value_mpa`` always records the canonical megapascal figure; ``target``
    labels the requested target unit (``MPa`` in the §7.2 canonical case).

    Raises:
        UnknownStressUnitError: if either unit symbol is unrecognised.
    """
    src = _resolve(from_unit)
    dst = _resolve(to_unit)
    return StressConversion(
        value_raw=value,
        from_unit=src,
        value_mpa=value * _MPA_PER_UNIT[src],
        target=dst,
    )
