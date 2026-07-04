"""Apples-to-apples unit normalization for the Comparison table — §7.5.

Values pulled from different sources land in the comparison table on different
units — a strength column may mix ``46.5 ksi``, ``320 N·mm⁻²`` and ``0.32 GPa``
which are numerically **incomparable at a glance** even though they describe the
same quantity. This router projects every cell onto a single *canonical* unit so
the table reads honestly: ``46.5 ksi``, ``320 N/mm²`` and ``0.32 GPa`` all line up
as ``≈ 320 MPa`` and can be ranked head-to-head (``ksi / N·mm⁻² / MPa → MPa``).

It reuses the already-built converters instead of reimplementing arithmetic:

* :func:`kg_common.units.stress_strength.to_mpa` — the §7.2 strength/stress family
  (``MPa`` / ``GPa`` / ``kPa`` / ``Pa`` / ``ksi`` / ``psi`` / ``N/mm2`` / ``kgf/mm2``),
  whose canonical target is ``MPa``;
* :func:`kg_common.units.conversions.convert` — the general §7.10 registry for the
  other dimensions (temperature, pressure, energy, length, fraction).

Two endpoints, both pure compute (no graph I/O):

* ``GET  /api/v1/comparison/units``      — units this normalizer understands, grouped
  by dimension with the canonical target of each (for UI pickers).
* ``POST /api/v1/comparison/normalize``  — a set of ``(label, value, unit)`` cells →
  the same cells with ``value_normalized`` / ``normalized_unit`` / ``normalization_method``
  filled, a common canonical unit for the column, and the min/max/spread.

A cell whose unit belongs to a different physical dimension than the column target
(or is unknown / missing) is returned with ``value_normalized = null`` and an honest
``normalization_method`` ("incompatible" / "unit_missing") — never silently coerced.
"""

from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from kg_common.units.conversions import (
    IncompatibleUnitsError,
    UnknownUnitError,
    convert,
    dimension_of,
    is_known_unit,
)
from kg_common.units.stress_strength import (
    CANONICAL as STRESS_CANONICAL,
)
from kg_common.units.stress_strength import (
    UnknownStressUnitError,
    to_mpa,
)

router = APIRouter(prefix="/api/v1/comparison", tags=["comparison"])

# Canonical target unit per physical dimension. Stress/strength units all fold
# onto MPa (§7.2); the other families onto the reader-friendly working unit.
STRESS = "stress"
_CANONICAL_BY_DIM: dict[str, str] = {
    STRESS: STRESS_CANONICAL,  # MPa
    "temperature": "°C",
    "pressure": "MPa",
    "energy": "kJ",
    "length": "mm",
    "fraction": "%",
}

# Human-facing catalogue of units per dimension (drives the UI unit picker).
_STRESS_UNITS = ("MPa", "GPa", "kPa", "Pa", "ksi", "psi", "N/mm2", "kgf/mm2")
_UNIT_CATALOGUE: dict[str, tuple[str, ...]] = {
    STRESS: _STRESS_UNITS,
    "temperature": ("°C", "K", "°F"),
    "pressure": ("MPa", "kPa", "bar", "atm", "psi"),
    "energy": ("J", "kJ", "cal", "kcal", "eV"),
    "length": ("nm", "µm", "mm", "m"),
    "fraction": ("%", "ppm", "fraction"),
}

_DIM_LABELS_RU: dict[str, str] = {
    STRESS: "прочность / напряжение",
    "temperature": "температура",
    "pressure": "давление",
    "energy": "энергия",
    "length": "длина",
    "fraction": "доля / концентрация",
}


def _fold(unit: str) -> str:
    """NFKC-fold a unit token for identity comparison (case preserved)."""
    return unicodedata.normalize("NFKC", str(unit)).strip()


def _is_stress(unit: str) -> bool:
    """True iff *unit* is a known strength/stress unit (ksi, N/mm2, GPa, …)."""
    try:
        to_mpa(1.0, unit)
    except UnknownStressUnitError:
        return False
    return True


def _canonical_for(unit: str) -> str | None:
    """Canonical target unit for *unit*'s dimension, or ``None`` if unknown.

    Strength units resolve to ``MPa`` even when they overlap the pressure family
    (``MPa`` / ``kPa`` / ``psi``), so a strength column normalizes to megapascals.
    """
    if _is_stress(unit):
        return _CANONICAL_BY_DIM[STRESS]
    if is_known_unit(unit):
        return _CANONICAL_BY_DIM.get(dimension_of(unit))
    return None


def _convert(value: float, unit: str, target: str) -> float:
    """Convert *value* from *unit* to *target* — reuses the §7.2/§7.10 converters.

    Tries the strength/stress registry first (it alone carries ``ksi`` / ``N/mm2``
    / ``GPa`` / ``kgf/mm2``); falls back to the general dimension registry. Raises
    :class:`UnknownUnitError` / :class:`IncompatibleUnitsError` when the pair is
    unconvertible so the caller can flag the cell honestly.
    """
    if _is_stress(unit) and _is_stress(target):
        # Route через MPa: (MPa per source) / (MPa per target).
        return value * to_mpa(1.0, unit) / to_mpa(1.0, target)
    return convert(value, unit, target)


def _round(x: float) -> float:
    """Round to a compact, table-friendly precision without noisy trailing digits."""
    if x == 0.0:
        return 0.0
    r = round(x, 6)
    return int(r) if float(r).is_integer() else r


# --------------------------------------------------------------------------- IO
class Cell(BaseModel):
    """One comparison cell to normalize — ячейка сравнения (§7.5)."""

    label: str = Field("", description="Optional row/source label")
    value: float = Field(..., description="Numeric magnitude in `unit`")
    unit: str = Field("", description="Source unit, e.g. 'ksi', 'N/mm²', 'GPa'")


class NormalizeRequest(BaseModel):
    cells: list[Cell] = Field(default_factory=list)
    target_unit: str | None = Field(
        None,
        description="Canonical unit to normalize onto; inferred from the cells when omitted.",
    )


class NormalizedCell(BaseModel):
    label: str
    value_raw: float
    unit: str
    value_normalized: float | None
    normalized_unit: str | None
    normalization_method: str  # direct | converted | incompatible | unit_missing
    note: str = ""


class NormalizeResponse(BaseModel):
    target_unit: str | None
    cells: list[NormalizedCell]
    all_comparable: bool
    min: float | None
    max: float | None
    spread: float | None
    best_label: str | None
    worst_label: str | None


@router.get("/units")
def units(_role: str = Depends(current_role)) -> dict:
    """Units this normalizer understands, grouped by dimension (§7.5)."""
    return {
        "dimensions": [
            {
                "dimension": dim,
                "label_ru": _DIM_LABELS_RU.get(dim, dim),
                "canonical": _CANONICAL_BY_DIM[dim],
                "units": list(us),
            }
            for dim, us in _UNIT_CATALOGUE.items()
        ],
        "note": "ksi / N·mm⁻² / GPa / kgf·mm⁻² → MPa; каждая колонка приводится к одной единице.",
    }


@router.post("/normalize", response_model=NormalizeResponse)
def normalize(req: NormalizeRequest, _role: str = Depends(current_role)) -> NormalizeResponse:
    """Project comparison cells onto one canonical unit — apples-to-apples (§7.5).

    Turns a mixed ``46.5 ksi`` / ``320 N/mm²`` / ``0.32 GPa`` column into a single
    ``≈ 320 MPa`` comparable set so the table can be read and ranked honestly.
    """
    if not req.cells:
        raise HTTPException(status_code=422, detail="at least one cell is required")

    # Resolve the column target: caller-supplied, else inferred from the first
    # cell that carries a recognisable unit.
    target = _fold(req.target_unit) if req.target_unit else None
    if target is not None and _canonical_for(target) is None:
        raise HTTPException(status_code=422, detail=f"unknown target unit {req.target_unit!r}")
    if target is None:
        for c in req.cells:
            if c.unit.strip():
                cand = _canonical_for(c.unit)
                if cand is not None:
                    target = cand
                    break

    out: list[NormalizedCell] = []
    for c in req.cells:
        raw_unit = c.unit.strip()
        if not raw_unit:
            out.append(
                NormalizedCell(
                    label=c.label.strip(),
                    value_raw=c.value,
                    unit="",
                    value_normalized=None,
                    normalized_unit=target,
                    normalization_method="unit_missing",
                    note="значение без единицы — несравнимо",
                )
            )
            continue

        if target is None:
            out.append(
                NormalizedCell(
                    label=c.label.strip(),
                    value_raw=c.value,
                    unit=raw_unit,
                    value_normalized=None,
                    normalized_unit=None,
                    normalization_method="incompatible",
                    note=f"неизвестная единица {raw_unit!r}",
                )
            )
            continue

        try:
            nv = _convert(c.value, raw_unit, target)
        except (UnknownUnitError, IncompatibleUnitsError, UnknownStressUnitError):
            out.append(
                NormalizedCell(
                    label=c.label.strip(),
                    value_raw=c.value,
                    unit=raw_unit,
                    value_normalized=None,
                    normalized_unit=None,
                    normalization_method="incompatible",
                    note=f"{raw_unit} не приводится к {target}",
                )
            )
            continue

        direct = _fold(raw_unit) == _fold(target)
        out.append(
            NormalizedCell(
                label=c.label.strip(),
                value_raw=c.value,
                unit=raw_unit,
                value_normalized=_round(nv),
                normalized_unit=target,
                normalization_method="direct" if direct else "converted",
                note="" if direct else f"{c.value} {raw_unit} = {_round(nv)} {target}",
            )
        )

    comparable = [c for c in out if c.value_normalized is not None]
    all_comparable = len(comparable) == len(out)
    vals = [(c.value_normalized, c.label) for c in comparable if c.value_normalized is not None]
    if vals:
        lo = min(vals, key=lambda t: t[0])
        hi = max(vals, key=lambda t: t[0])
        vmin, vmax = lo[0], hi[0]
        spread = _round(vmax - vmin)
        worst_label, best_label = lo[1] or None, hi[1] or None
    else:
        vmin = vmax = spread = None
        best_label = worst_label = None

    return NormalizeResponse(
        target_unit=target,
        cells=out,
        all_comparable=all_comparable,
        min=vmin,
        max=vmax,
        spread=spread,
        best_label=best_label,
        worst_label=worst_label,
    )
