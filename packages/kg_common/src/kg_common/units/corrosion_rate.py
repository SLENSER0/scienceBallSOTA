"""Corrosion-rate canonical target ``mm/year`` — скорость коррозии (§7.2).

The extended unit registry (:mod:`kg_common.units.conversions`) routes values
within a single physical dimension, but it carries **no per-time rate** — and no
other module models corrosion penetration rate. This module fills that gap with
a small, ``pint``-free converter whose canonical target is **mm/year**.

Supported source units:

* ``mm/year``            — penetration rate, the canonical unit (factor ``1``);
* ``mpy``               — mils (thousandths of an inch) per year, ``0.0254``;
* ``um/year``           — micrometres per year, ``1e-3``;
* ``nm/year``           — nanometres per year, ``1e-6``;
* ``g/(m2*day)``        — mass-loss rate (grams per m² per day, «gmd»/«mdd»),
  converted via ``mm/yr = 0.365 · gmd / density_g_cm3`` — **requires** the
  material density, otherwise :class:`ValueError` is raised.

Public API:

* :class:`CorrosionRate`        — frozen result (value, unit, mm_per_year, method).
* :func:`to_mm_per_year`        — any supported unit → mm/year (canonical).
* :func:`convert_corrosion_rate` — value between two supported units.

Pure Python, no I/O and no ``pint`` dependency. // Чистый Python, без pint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# Linear factors: ``mm/year = value · factor`` (mass-loss handled separately,
# as it also depends on density). // Линейные коэффициенты к mm/year.
# ---------------------------------------------------------------------------
_LINEAR_FACTORS: dict[str, float] = {
    "mm/year": 1.0,
    "mpy": 0.0254,  # 1 mil = 0.0254 mm
    "um/year": 1e-3,  # micrometre → millimetre
    "nm/year": 1e-6,  # nanometre → millimetre
}

# Mass-loss units routed through ``mm/yr = 0.365 · gmd / density`` (§7.2).
_MASS_LOSS_UNITS: frozenset[str] = frozenset({"g/(m2*day)"})

# ``0.365`` = 365 days · 1e-3 (g·m⁻²·day⁻¹ → mm/year given density in g/cm³).
_GMD_CONSTANT: float = 0.365


@dataclass(frozen=True)
class CorrosionRate:
    """A corrosion rate resolved to its canonical ``mm/year`` value.

    Attributes:
        value: The magnitude in :attr:`unit`.
        unit: The (target) unit symbol this magnitude is expressed in.
        mm_per_year: The canonical penetration rate in ``mm/year``.
        method: ``"direct"`` (same unit) or ``"converted"`` (cross-unit).
    """

    value: float
    unit: str
    mm_per_year: float
    method: str

    def as_dict(self) -> dict[str, object]:
        """Return the four fields as a plain dict. // Вернуть поля словарём."""
        return asdict(self)


def _normalise(unit: str) -> str:
    """Canonicalise a unit string (trim, lower-case). // Нормализация единицы."""
    return unit.strip().lower()


def to_mm_per_year(
    value: float,
    unit: str,
    density_g_cm3: float | None = None,
) -> float:
    """Convert *value* in *unit* to the canonical ``mm/year``.

    Mass-loss units (``g/(m2*day)``) require *density_g_cm3*; a missing density
    raises :class:`ValueError`. An unknown unit also raises :class:`ValueError`.
    """
    key = _normalise(unit)
    if key in _LINEAR_FACTORS:
        return value * _LINEAR_FACTORS[key]
    if key in _MASS_LOSS_UNITS:
        if density_g_cm3 is None:
            raise ValueError(f"unit {unit!r} is a mass-loss rate and requires density_g_cm3")
        if density_g_cm3 <= 0:
            raise ValueError(f"density_g_cm3 must be > 0, got {density_g_cm3!r}")
        return _GMD_CONSTANT * value / density_g_cm3
    raise ValueError(f"unknown corrosion-rate unit: {unit!r}")


def _from_mm_per_year(
    mm_per_year: float,
    unit: str,
    density_g_cm3: float | None = None,
) -> float:
    """Convert a canonical ``mm/year`` magnitude out to *unit*."""
    key = _normalise(unit)
    if key in _LINEAR_FACTORS:
        return mm_per_year / _LINEAR_FACTORS[key]
    if key in _MASS_LOSS_UNITS:
        if density_g_cm3 is None:
            raise ValueError(f"unit {unit!r} is a mass-loss rate and requires density_g_cm3")
        if density_g_cm3 <= 0:
            raise ValueError(f"density_g_cm3 must be > 0, got {density_g_cm3!r}")
        return mm_per_year * density_g_cm3 / _GMD_CONSTANT
    raise ValueError(f"unknown corrosion-rate unit: {unit!r}")


def convert_corrosion_rate(
    value: float,
    from_unit: str,
    to_unit: str,
    density_g_cm3: float | None = None,
) -> CorrosionRate:
    """Convert *value* from *from_unit* to *to_unit*, canonicalised via mm/year.

    ``method`` is ``"direct"`` when the units coincide (after normalisation) and
    ``"converted"`` otherwise. Unknown units — and mass-loss units without a
    density — raise :class:`ValueError`.
    """
    mm_per_year = to_mm_per_year(value, from_unit, density_g_cm3)
    same = _normalise(from_unit) == _normalise(to_unit)
    if same:
        return CorrosionRate(
            value=value,
            unit=to_unit,
            mm_per_year=mm_per_year,
            method="direct",
        )
    out_value = _from_mm_per_year(mm_per_year, to_unit, density_g_cm3)
    return CorrosionRate(
        value=out_value,
        unit=to_unit,
        mm_per_year=mm_per_year,
        method="converted",
    )
