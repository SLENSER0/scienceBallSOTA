"""Hardness scale conversion for metallurgy measurements (§7.3 / §6.3).

Converts between Vickers (HV), Brinell (HB) and Rockwell-C (HRC) and estimates
ultimate tensile strength, so measurements reported on different scales can be
compared. Values are **approximate**, based on the standard steel conversion
table (ASTM E140 / SAE J417) and linearly interpolated — every result carries
``approximate=True`` and a note, so downstream logic (and curators) treat a
converted value with appropriate uncertainty rather than as ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

HARDNESS_SCALES = ("HV", "HB", "HRC")

# Steel conversion table (approximate). Columns: HV, HB, HRC, tensile_MPa.
# None = not defined/meaningful on that scale at that hardness.
_TABLE: list[tuple[float, float | None, float | None, float | None]] = [
    (100, 95, None, 320),
    (150, 143, None, 490),
    (200, 190, None, 665),
    (250, 238, 22, 820),
    (300, 285, 30, 995),
    (350, 333, 36, 1155),
    (400, 380, 41, 1290),
    (450, 428, 45, 1435),
    (500, 475, 49, 1595),
    (550, 522, 52, 1755),
    (600, 570, 55, 1920),
    (650, None, 58, 2100),
    (700, None, 60, None),
    (750, None, 62, None),
    (800, None, 64, None),
]
_COL = {"HV": 0, "HB": 1, "HRC": 2}


@dataclass(frozen=True)
class HardnessConversion:
    value: float
    scale: str
    approximate: bool = True
    note: str = ""


def _pairs(x_col: int, y_col: int) -> list[tuple[float, float]]:
    """Sorted (x, y) pairs where both columns are defined."""
    pts = [(r[x_col], r[y_col]) for r in _TABLE if r[x_col] is not None and r[y_col] is not None]
    return sorted(pts)  # type: ignore[arg-type]


def _interp(x: float, pairs: list[tuple[float, float]]) -> tuple[float, bool]:
    """Linear interpolation; returns (y, clamped)."""
    if x <= pairs[0][0]:
        return pairs[0][1], x < pairs[0][0]
    if x >= pairs[-1][0]:
        return pairs[-1][1], x > pairs[-1][0]
    for (x0, y0), (x1, y1) in pairwise(pairs):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + t * (y1 - y0), False
    return pairs[-1][1], True


def _to_hv(value: float, scale: str) -> float:
    if scale == "HV":
        return value
    hv, _ = _interp(value, _pairs(_COL[scale], 0))
    return hv


def convert_hardness(value: float, from_scale: str, to_scale: str) -> HardnessConversion:
    """Convert *value* from one hardness scale to another (steel, approximate)."""
    fs, ts = from_scale.upper(), to_scale.upper()
    if fs not in _COL or ts not in _COL:
        raise ValueError(f"unsupported hardness scale: {from_scale!r}/{to_scale!r}")
    if fs == ts:
        return HardnessConversion(value, ts, approximate=False, note="identity")
    hv = _to_hv(value, fs)
    out, clamped = _interp(hv, _pairs(0, _COL[ts]))
    note = f"{fs}{value:g}→{ts} via steel ASTM E140 table"
    if clamped:
        note += " (out of table range — clamped)"
    return HardnessConversion(round(out, 1), ts, approximate=True, note=note)


def hv_to_tensile_mpa(hv: float) -> HardnessConversion:
    """Estimate ultimate tensile strength (MPa) from Vickers hardness (steel)."""
    out, clamped = _interp(hv, _pairs(0, 3))
    note = "HV→UTS (steel, ~3.4·HB rule / E140)"
    if clamped:
        note += " (out of table range — clamped)"
    return HardnessConversion(round(out, 0), "MPa", approximate=True, note=note)
