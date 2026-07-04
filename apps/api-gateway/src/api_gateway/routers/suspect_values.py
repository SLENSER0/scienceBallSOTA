"""Suspect-value flags for the Evidence Inspector & curation queue — §7.7.

The units library already *computes* the three §7.7 anomaly signals; nothing yet
**surfaces** them to a human. This router is that surface: it scans the live
``Measurement`` population in the graph and, reusing the already-built detectors,
attaches a badge to every value that looks wrong so a curator (or the Evidence
Inspector) sees «подозрительное значение» at a glance and OCR / unit-scale
blunders (``0.32`` where the source meant ``320 MPa``) never slip through.

Three orthogonal signals, each mapped to a named flag from §7.7:

* ``SUSPECT_VALUE`` — a range sanity-check against the physical-range catalog
  (:mod:`kg_extractors.property_ranges`). A value **outside the hard physical
  range** is non-physical (``severity="hard_error"`` — an extraction/unit error,
  *not* indexed as a valid measurement, e.g. ``tensile_strength = -50 MPa``); a
  value inside the hard range but **outside the ordinary typical band** is
  plausible-but-flaggable (``severity="suspect"``, e.g. ``hardness = 5000 HV``)
  and routed to review without being discarded.
* ``statistical_outlier`` — a population outlier within the value's own
  ``(material_class, property)`` cohort, via :func:`kg_extractors.outliers.detect_outliers`
  (Tukey IQR fence **or** Iglewicz–Hoaglin robust z-score).
* ``unit_scale_suspect`` — a factor-10/100/1000 slip vs the cohort typical
  (:func:`kg_extractors.outliers.unit_scale_suspect`), enriched with a concrete
  repair suggestion from :func:`kg_common.units.scale_repair.suggest_scale_repair`
  when the property carries a plausibility band (``0.32 → ×1000 → 320``).

Two read-only endpoints (server profile, Neo4j :8000):

* ``GET /api/v1/suspect-values/queue`` — the curation review queue: every flagged
  measurement, most-severe first, with per-flag counts (§12.1 review queue link).
* ``GET /api/v1/suspect-values/measurement/{node_id}`` — the badge set for one
  measurement, computed against the whole population, for the Evidence Inspector.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/suspect-values", tags=["suspect-values"])

# --- named §7.7 flags --------------------------------------------------------
FLAG_SUSPECT = "SUSPECT_VALUE"
FLAG_OUTLIER = "statistical_outlier"
FLAG_SCALE = "unit_scale_suspect"

# --- severities (последствия отличаются) -------------------------------------
SEV_HARD = "hard_error"  # non-physical → не индексируется как валидное
SEV_SUSPECT = "suspect"  # вне типичной полосы → в review, но допускается
SEV_OUTLIER = "outlier"  # статистический выброс популяции → на ревью
SEV_SCALE = "scale"  # вероятная ошибка масштаба ×10/×100/×1000

# Severity ranking for queue ordering & the "worst" badge (наибольшая тяжесть).
_SEV_RANK = {SEV_HARD: 3, SEV_SUSPECT: 2, SEV_OUTLIER: 1, SEV_SCALE: 1}

_FLAG_LABEL_RU: dict[str, str] = {
    FLAG_SUSPECT: "подозрительное значение",
    FLAG_OUTLIER: "статистический выброс",
    FLAG_SCALE: "подозрение на ошибку масштаба",
}

# Cohort grouping key for the population outlier test (§7.7).
_GROUP_KEY = ("material_class", "property")


# --------------------------------------------------------------------------- IO
class SuspectBadge(BaseModel):
    """One anomaly badge on a measurement (§7.7)."""

    flag: str  # SUSPECT_VALUE | statistical_outlier | unit_scale_suspect
    severity: str  # hard_error | suspect | outlier | scale
    label_ru: str
    reason: str


class SuspectMeasurement(BaseModel):
    """A measurement with its §7.7 anomaly badges + detector context."""

    id: str
    name: str | None
    property_name: str | None
    property_id: str | None
    material: str | None
    material_class: str | None
    domain: str | None
    value: float
    unit: str | None
    value_raw: str | None
    badges: list[SuspectBadge]
    indexable: bool  # False when a hard_error is present (не индексируется)
    # range context (§7.7 property_ranges.yaml)
    hard_min: float | None = None
    hard_max: float | None = None
    typical_min: float | None = None
    typical_max: float | None = None
    # outlier context
    robust_z: float | None = None
    cohort_median: float | None = None
    cohort_n: int = 0
    # scale-repair context
    suggested_factor: float | None = None
    corrected_value: float | None = None


class QueueResponse(BaseModel):
    total_measurements: int
    flagged: int
    counts: dict[str, int]  # per-flag counts across the flagged set
    items: list[SuspectMeasurement]


# ------------------------------------------------------------------- graph read
_SCAN_CYPHER = (
    "MATCH (ms:Node) WHERE ms.label='Measurement' AND ms.value_normalized IS NOT NULL "
    "OPTIONAL MATCH (ms)-[:Rel {type:'ABOUT_MATERIAL'}]->(mat:Node) "
    "RETURN ms.id, ms.name, ms.property_name, ms.value_normalized, ms.normalized_unit, "
    "ms.domain, ms.value_raw, mat.name, "
    "coalesce(mat.material_class, ms.material_class, '') "
    "LIMIT $limit"
)


@dataclass
class _Row:
    id: str
    name: str | None
    property_name: str | None
    value: float
    unit: str | None
    domain: str | None
    value_raw: str | None
    material: str | None
    material_class: str | None


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _scan_rows(store, limit: int) -> list[_Row]:  # type: ignore[no-untyped-def]
    """Read Measurement nodes (+ their material) into typed rows, numeric only."""
    raw = store.rows(_SCAN_CYPHER, {"limit": int(limit)})
    out: list[_Row] = []
    for rec in raw:
        (mid, name, prop, val, unit, domain, vraw, mat_name, mat_class) = rec
        v = _to_float(val)
        if not mid or v is None:
            continue
        out.append(
            _Row(
                id=str(mid),
                name=name,
                property_name=prop,
                value=v,
                unit=unit,
                domain=domain,
                value_raw=str(vraw) if vraw not in (None, "") else None,
                material=mat_name,
                material_class=(str(mat_class) or None) if mat_class else None,
            )
        )
    return out


def _property_id(property_name: str | None) -> str | None:
    """Map a graph ``property_name`` to a canonical ``prop:*`` id (§6.6/§7.7)."""
    if not property_name:
        return None
    from kg_extractors.property_vocab import load_property_vocab

    vocab = _vocab_cache(load_property_vocab)
    hit = vocab.canonical_for(property_name)
    if hit:
        return hit
    # Fallback: measurements often store the bare canonical slug ("hardness").
    candidate = f"prop:{str(property_name).strip().lower()}"
    return candidate


_VOCAB = None


def _vocab_cache(loader):  # type: ignore[no-untyped-def]
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = loader()
    return _VOCAB


def _evaluate(rows: list[_Row]) -> list[SuspectMeasurement]:
    """Compute §7.7 badges for every row against the whole population."""
    from kg_extractors.outliers import detect_outliers, unit_scale_suspect
    from kg_extractors.property_ranges import default_property_ranges

    ranges = default_property_ranges()

    # 1) Population outlier pass (aligned to row order — все value числовые).
    outlier_rows = [
        {
            "value": r.value,
            "material_class": r.material_class or "",
            "property": r.property_name or "",
        }
        for r in rows
    ]
    flags = detect_outliers(outlier_rows, group_key=_GROUP_KEY)

    # 2) Cohort medians / sizes for the scale-slip heuristic.
    cohorts: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        cohorts.setdefault((r.material_class or "", r.property_name or ""), []).append(r.value)
    medians = {k: _median(v) for k, v in cohorts.items()}
    sizes = {k: len(v) for k, v in cohorts.items()}

    out: list[SuspectMeasurement] = []
    for r, of in zip(rows, flags, strict=False):
        pid = _property_id(r.property_name)
        entry = ranges.entry(pid) if pid else None
        cohort_key = (r.material_class or "", r.property_name or "")
        cohort_med = medians.get(cohort_key)
        cohort_n = sizes.get(cohort_key, 0)

        badges: list[SuspectBadge] = []
        indexable = True

        # --- SUSPECT_VALUE (range sanity check, §7.7) ------------------------
        hard_min = hard_max = typ_min = typ_max = None
        if entry is not None:
            hard_min, hard_max = entry.hard_min, entry.hard_max
            typ_min, typ_max = entry.typical_min, entry.typical_max
            if not entry.contains(r.value):
                indexable = False
                badges.append(
                    SuspectBadge(
                        flag=FLAG_SUSPECT,
                        severity=SEV_HARD,
                        label_ru=_FLAG_LABEL_RU[FLAG_SUSPECT],
                        reason=(
                            f"{_fmt(r.value)} {entry.unit} вне физического диапазона "
                            f"[{_fmt(hard_min)}, {_fmt(hard_max)}] — нефизично, не индексируется"
                        ),
                    )
                )
            elif not (typ_min <= r.value <= typ_max):
                badges.append(
                    SuspectBadge(
                        flag=FLAG_SUSPECT,
                        severity=SEV_SUSPECT,
                        label_ru=_FLAG_LABEL_RU[FLAG_SUSPECT],
                        reason=(
                            f"{_fmt(r.value)} {entry.unit} вне типичной полосы "
                            f"[{_fmt(typ_min)}, {_fmt(typ_max)}] — на ревью"
                        ),
                    )
                )

        # --- statistical_outlier (population, §7.7) --------------------------
        if of.is_outlier:
            badges.append(
                SuspectBadge(
                    flag=FLAG_OUTLIER,
                    severity=SEV_OUTLIER,
                    label_ru=_FLAG_LABEL_RU[FLAG_OUTLIER],
                    reason=(
                        f"выброс в когорте «{r.material_class or '—'} · {r.property_name or '—'}» "
                        f"(n={cohort_n}, robust z={of.score:.2f}, метод {of.method})"
                    ),
                )
            )

        # --- unit_scale_suspect (factor 10/100/1000, §7.7) -------------------
        factor = corrected = None
        scale_hit = (
            cohort_med is not None
            and cohort_n >= 3
            and unit_scale_suspect(r.value, cohort_med)
        )
        repair = _scale_repair(pid, r.value) if pid else None
        if repair is not None and not repair.in_band and repair.suggested_factor != 1.0:
            factor = repair.suggested_factor
            corrected = repair.corrected_value
            scale_hit = True
        if scale_hit:
            if factor is not None:
                reason = (
                    f"вероятная ошибка масштаба: ×{_fmt(factor)} → {_fmt(corrected)} "
                    f"(типичное ≈ {_fmt(cohort_med)})"
                )
            else:
                reason = (
                    f"значение {_fmt(r.value)} отстоит от типичного ≈ {_fmt(cohort_med)} "
                    f"на порядок величины"
                )
            badges.append(
                SuspectBadge(
                    flag=FLAG_SCALE,
                    severity=SEV_SCALE,
                    label_ru=_FLAG_LABEL_RU[FLAG_SCALE],
                    reason=reason,
                )
            )

        out.append(
            SuspectMeasurement(
                id=r.id,
                name=r.name,
                property_name=r.property_name,
                property_id=pid if entry is not None else None,
                material=r.material,
                material_class=r.material_class,
                domain=r.domain,
                value=r.value,
                unit=r.unit,
                value_raw=r.value_raw,
                badges=badges,
                indexable=indexable,
                hard_min=hard_min,
                hard_max=hard_max,
                typical_min=typ_min,
                typical_max=typ_max,
                robust_z=round(of.score, 3),
                cohort_median=cohort_med,
                cohort_n=cohort_n,
                suggested_factor=factor,
                corrected_value=corrected,
            )
        )
    return out


def _scale_repair(property_id: str | None, value: float):  # type: ignore[no-untyped-def]
    """Best-effort scale-repair suggestion; ``None`` when no policy band exists."""
    if not property_id:
        return None
    try:
        from kg_common.units.scale_repair import suggest_scale_repair

        rep = suggest_scale_repair(value, property_id)
    except Exception:  # never let a missing band break the queue
        return None
    # A property with no plausibility band yields factor 1.0 / not-in-band; treat
    # that as "no suggestion" so we fall back to the cohort-median heuristic.
    if rep.suggested_factor == 1.0 and not rep.in_band:
        return None
    return rep


def _worst_rank(m: SuspectMeasurement) -> int:
    return max((_SEV_RANK.get(b.severity, 0) for b in m.badges), default=0)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    import statistics as st

    return round(st.median(values), 6)


def _fmt(x: float | None) -> str:
    if x is None:
        return "—"
    r = round(float(x), 4)
    return str(int(r) if float(r).is_integer() else r)


# ------------------------------------------------------------------- endpoints
@router.get("/queue", response_model=QueueResponse)
def queue(
    limit: int = Query(default=2000, ge=1, le=20000),
    flag: str | None = Query(default=None, description="фильтр по флагу"),
    severity: str | None = Query(default=None, description="фильтр по тяжести"),
) -> QueueResponse:
    """Curation review queue of §7.7-flagged measurements, most-severe first.

    Scans up to *limit* ``Measurement`` nodes, evaluates the three anomaly
    signals against the whole population and returns only the flagged ones with
    per-flag counts, so a curator triages OCR / unit-scale errors in one place.
    """
    store = get_store()
    rows = _scan_rows(store, limit)
    evaluated = _evaluate(rows)

    flagged = [m for m in evaluated if m.badges]
    if flag:
        flagged = [m for m in flagged if any(b.flag == flag for b in m.badges)]
    if severity:
        flagged = [m for m in flagged if any(b.severity == severity for b in m.badges)]

    flagged.sort(key=lambda m: (_worst_rank(m), abs(m.robust_z or 0.0)), reverse=True)

    counts: dict[str, int] = {FLAG_SUSPECT: 0, FLAG_OUTLIER: 0, FLAG_SCALE: 0}
    for m in flagged:
        for f in {b.flag for b in m.badges}:
            counts[f] = counts.get(f, 0) + 1

    return QueueResponse(
        total_measurements=len(evaluated),
        flagged=len(flagged),
        counts=counts,
        items=flagged,
    )


@router.get("/measurement/{node_id}", response_model=SuspectMeasurement)
def measurement(
    node_id: str, limit: int = Query(default=2000, ge=1, le=20000)
) -> SuspectMeasurement:
    """§7.7 badges for one measurement (Evidence Inspector), scored vs the population.

    The cohort-relative signals (outlier, scale slip) require the full peer
    population, so the whole ``Measurement`` set is scanned and the requested
    node projected out — never judged in isolation.
    """
    store = get_store()
    rows = _scan_rows(store, limit)
    evaluated = _evaluate(rows)
    for m in evaluated:
        if m.id == node_id:
            return m
    raise HTTPException(status_code=404, detail=f"measurement {node_id!r} not found or non-numeric")
