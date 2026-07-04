"""Cross-scale hardness comparison HV↔HRC↔HB (ASTM E140) — §7.3.

The metallurgy corpus reports hardness on three incompatible scales (Vickers
``HV``, Brinell ``HB``, Rockwell-C ``HRC``) that ``pint`` cannot interconvert
(the scales are non-linear and standard-dependent). Comparing ``30 HRC`` against
``302 HV`` head-to-head is an apples-to-oranges error the comparison-invariant
guard (§24.13) deliberately *refuses*.

This router puts the already-built :func:`kg_common.units.hardness.convert_hardness`
to work at query time so those readings become comparable: every value is projected
onto a common scale via the ASTM E140 steel table (linearly interpolated), so
``30 HRC ≈ 302 HV ≈ 286 HB ≈ 995 MPa`` UTS can be lined up and ranked. Results are
**approximate** (``normalization_method="rule"``, ``conversion_standard="ASTM E140"``)
and carry the source scale — the converter never silently overwrites ground truth.

Two endpoints, both pure compute (no graph I/O):

- ``POST /api/v1/hardness/equivalents`` — one reading → its HV/HB/HRC equivalents
  plus an estimated ultimate tensile strength.
- ``POST /api/v1/hardness/compare`` — several readings on mixed scales → a single
  leaderboard normalised to one target scale, with the spread and the hardest pick.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from kg_common.units.hardness import (
    HARDNESS_SCALES,
    convert_hardness,
    hv_to_tensile_mpa,
)

router = APIRouter(prefix="/api/v1/hardness", tags=["hardness"])

CONVERSION_STANDARD = "ASTM E140"
NORMALIZATION_METHOD = "rule"


class EquivalentsRequest(BaseModel):
    value: float = Field(..., description="Numeric hardness reading, e.g. 30")
    scale: str = Field(..., description="Source scale: HV, HB or HRC")


class ScaleValue(BaseModel):
    scale: str
    value: float | None
    is_source: bool = False


class EquivalentsResponse(BaseModel):
    input: ScaleValue
    equivalents: list[ScaleValue]
    tensile_mpa: float | None
    approximate: bool
    conversion_standard: str = CONVERSION_STANDARD
    normalization_method: str = NORMALIZATION_METHOD
    notes: list[str]


class Reading(BaseModel):
    label: str = Field("", description="Optional row label (material/regime/source)")
    value: float
    scale: str


class CompareRequest(BaseModel):
    readings: list[Reading] = Field(default_factory=list)
    target_scale: str = Field("HV", description="Common scale to normalise onto")


class CompareRow(BaseModel):
    label: str
    original_value: float
    original_scale: str
    normalized_value: float | None
    normalized_scale: str
    hv: float | None  # canonical HV used for ranking
    tensile_mpa: float | None
    approximate: bool
    note: str


class CompareResponse(BaseModel):
    target_scale: str
    rows: list[CompareRow]
    hardest: str | None
    softest: str | None
    spread_hv: float | None
    conversion_standard: str = CONVERSION_STANDARD
    normalization_method: str = NORMALIZATION_METHOD


def _norm_scale(scale: str) -> str:
    s = (scale or "").strip().upper()
    if s not in HARDNESS_SCALES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported hardness scale {scale!r}; expected one of {list(HARDNESS_SCALES)}",
        )
    return s


@router.get("/scales")
def scales(_role: str = Depends(current_role)) -> dict:
    """The hardness scales this converter understands (for UI pickers)."""
    return {
        "scales": list(HARDNESS_SCALES),
        "conversion_standard": CONVERSION_STANDARD,
        "note": "steel table, approximate, linearly interpolated (ASTM E140 / SAE J417)",
    }


@router.post("/equivalents", response_model=EquivalentsResponse)
def equivalents(req: EquivalentsRequest, _role: str = Depends(current_role)) -> EquivalentsResponse:
    """Project one reading onto every hardness scale + an estimated UTS (§7.3)."""
    src = _norm_scale(req.scale)
    notes: list[str] = []
    approximate = False
    equivs: list[ScaleValue] = []
    for target in HARDNESS_SCALES:
        conv = convert_hardness(req.value, src, target)
        if conv.approximate:
            approximate = True
        if conv.note and target != src:
            notes.append(conv.note)
        equivs.append(
            ScaleValue(scale=target, value=conv.value, is_source=(target == src))
        )

    # Estimate ultimate tensile strength from the canonical HV value.
    hv = next((e.value for e in equivs if e.scale == "HV"), None)
    tensile: float | None = None
    if hv is not None:
        t = hv_to_tensile_mpa(hv)
        tensile = t.value
        notes.append(t.note)

    return EquivalentsResponse(
        input=ScaleValue(scale=src, value=req.value, is_source=True),
        equivalents=equivs,
        tensile_mpa=tensile,
        approximate=approximate,
        notes=notes,
    )


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, _role: str = Depends(current_role)) -> CompareResponse:
    """Normalise mixed-scale readings onto one scale and rank them (§7.3).

    Turns a pile of ``30 HRC`` / ``302 HV`` / ``286 HB`` readings into a single
    comparable leaderboard — the cross-scale comparison the invariant guard
    (§24.13) otherwise forbids on raw units.
    """
    target = _norm_scale(req.target_scale)
    if not req.readings:
        raise HTTPException(status_code=422, detail="at least one reading is required")

    rows: list[CompareRow] = []
    for i, r in enumerate(req.readings):
        src = _norm_scale(r.scale)
        to_target = convert_hardness(r.value, src, target)
        to_hv = convert_hardness(r.value, src, "HV")
        tensile = hv_to_tensile_mpa(to_hv.value).value if to_hv.value is not None else None
        rows.append(
            CompareRow(
                label=r.label.strip() or f"#{i + 1}",
                original_value=r.value,
                original_scale=src,
                normalized_value=to_target.value,
                normalized_scale=target,
                hv=to_hv.value,
                tensile_mpa=tensile,
                approximate=to_target.approximate,
                note=to_target.note,
            )
        )

    ranked = [row for row in rows if row.hv is not None]
    ranked.sort(key=lambda row: row.hv, reverse=True)  # type: ignore[arg-type,return-value]
    hardest = ranked[0].label if ranked else None
    softest = ranked[-1].label if ranked else None
    spread = (
        round(ranked[0].hv - ranked[-1].hv, 1)  # type: ignore[operator]
        if len(ranked) >= 2
        else (0.0 if ranked else None)
    )

    # Present rows hardest-first so the UI reads as a leaderboard.
    rows.sort(key=lambda row: (row.hv is not None, row.hv or 0.0), reverse=True)

    return CompareResponse(
        target_scale=target,
        rows=rows,
        hardest=hardest,
        softest=softest,
        spread_hv=spread,
    )
