"""Ambiguous / missing unit review queue + gap matrix — §7.6.

The normalization core already *decides*, honestly, that it must NOT guess: a
bare ``%`` in a composition context (``"2.5 %"``) has no ``wt``/``at``/``vol``
basis and is left ``unit_ambiguous`` rather than silently converted, and a bare
number with no unit (``"320"`` for ``tensile_strength``) is flagged
``missing_unit`` and emitted as a gap. Those detectors already exist and are
tested:

* :func:`kg_extractors.unit_ambiguous.detect_ambiguous_unit` — bare ``%``/``ppm``
  without a basis in a composition context ⇒ candidates ``wt%`` / ``at%`` /
  ``vol%`` (never a silent pick);
* :func:`kg_extractors.unit_problems.classify_problems` — value present but its
  (expected) unit absent ⇒ the ``missing_unit`` gap signal (unit-policy aware,
  so genuinely unitless properties such as pH are not mis-flagged).

Nothing yet **surfaces** them to a curator on the live graph. This router is that
surface — it scans the ``Measurement`` population (server profile, Neo4j :8000),
reuses the two already-built detectors, and returns:

* ``GET  /api/v1/unit-review/queue`` — the review queue: one entry per flagged
  measurement (``ambiguous_unit`` with disambiguation candidates, or
  ``missing_unit``), most-actionable first, each carrying its Evidence link
  (``doc_id`` / ``page``) so the curator sees the source — plus the
  ``gap_matrix`` (problem × domain counts) that drops ``missing_unit`` /
  ``ambiguous_unit`` into the Карта пробелов.
* ``POST /api/v1/unit-review/explain`` — pure-compute preview for an ad-hoc
  ``value_raw`` + ``property_context`` (mirrors the §7.6 acceptance criterion:
  ``"2.5 %"`` → ``unit_ambiguous``; ``"320"`` → ``missing_unit`` gap), so the
  behaviour is demonstrable even when the live graph carries no ambiguous data.

Read-only. No LLM, no writes — the detectors are pure; the router only reads the
graph and packages the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from kg_extractors.unit_ambiguous import detect_ambiguous_unit
from kg_extractors.unit_problems import classify_problems

router = APIRouter(prefix="/api/v1/unit-review", tags=["unit-review"])

# --- problem kinds (§7.6) ----------------------------------------------------
KIND_AMBIGUOUS = "ambiguous_unit"  # % / ppm без базиса wt/at/vol — не угадываем
KIND_MISSING = "missing_unit"  # значение без единицы — gap (§11.1)

_KIND_LABEL_RU: dict[str, str] = {
    KIND_AMBIGUOUS: "неоднозначная единица",
    KIND_MISSING: "нет единицы",
}

#: Reason shown for a value whose unit is simply absent (не угадываем).
_MISSING_REASON = "значение есть, единица отсутствует — не угадываем (gap missing_unit, §11.1)"

# missing_unit ranks above ambiguous for triage: a bare number is unusable,
# an ambiguous % is at least a known magnitude awaiting a basis pick.
_KIND_RANK: dict[str, int] = {KIND_MISSING: 2, KIND_AMBIGUOUS: 1}


# --------------------------------------------------------------------------- IO
class UnitReviewTask(BaseModel):
    """One flagged measurement awaiting a curator's unit decision (§7.6)."""

    id: str
    kind: str  # ambiguous_unit | missing_unit
    kind_ru: str
    name: str | None = None
    property_name: str | None = None
    property_id: str | None = None
    material: str | None = None
    domain: str | None = None
    value: float | None = None
    value_raw: str | None = None
    unit: str | None = None
    candidates: list[str] = Field(default_factory=list)  # wt% / at% / vol% (ambiguous)
    reason: str = ""
    gap_type: str = KIND_MISSING  # feeds the Карта пробелов (§11.1)
    # Evidence link (§8.3) — curator sees the source.
    doc_id: str | None = None
    page: int | None = None


class QueueResponse(BaseModel):
    """Review queue + gap matrix for §7.6 unit problems."""

    total_measurements: int
    flagged: int
    counts: dict[str, int]  # per-kind counts across the flagged set
    gap_matrix: dict[str, dict[str, int]]  # {kind: {domain: count}} — Карта пробелов
    tasks: list[UnitReviewTask]


class ExplainRequest(BaseModel):
    """Ad-hoc value to diagnose (mirrors ``normalize_measurement`` inputs)."""

    value_raw: str = Field(..., description="сырое значение, напр. '2.5 %' или '320'")
    property_context: str | None = Field(
        default=None, description="контекст свойства, напр. 'composition' / 'tensile_strength'"
    )
    unit: str | None = Field(default=None, description="явная единица, если отделена от значения")


class ExplainResponse(BaseModel):
    """Pure-compute §7.6 verdict for one ad-hoc value."""

    kind: str | None  # ambiguous_unit | missing_unit | None (clean)
    kind_ru: str | None
    unit_ambiguous: bool
    unit_missing: bool
    candidates: list[str] = Field(default_factory=list)
    reason: str = ""
    is_missing_unit_gap: bool = False
    review_task: dict[str, object] | None = None


# ------------------------------------------------------------------- graph read
_SCAN_CYPHER = (
    "MATCH (ms:Node) WHERE ms.label='Measurement' "
    "OPTIONAL MATCH (ms)-[:Rel {type:'ABOUT_MATERIAL'}]->(mat:Node) "
    "RETURN ms.id, ms.name, ms.property_name, ms.value_normalized, ms.normalized_unit, "
    "ms.unit, ms.value_raw, ms.domain, ms.doc_id, ms.page, mat.name "
    "LIMIT $limit"
)


@dataclass
class _Row:
    id: str
    name: str | None
    property_name: str | None
    value_normalized: float | None
    normalized_unit: str | None
    unit: str | None
    value_raw: str | None
    domain: str | None
    doc_id: str | None
    page: int | None
    material: str | None


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


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _clean_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _scan_rows(store, limit: int) -> list[_Row]:  # type: ignore[no-untyped-def]
    raw = store.rows(_SCAN_CYPHER, {"limit": int(limit)})
    out: list[_Row] = []
    for rec in raw:
        (mid, name, prop, vnorm, nunit, unit, vraw, domain, doc_id, page, mat_name) = rec
        if not mid:
            continue
        out.append(
            _Row(
                id=str(mid),
                name=_clean_str(name),
                property_name=_clean_str(prop),
                value_normalized=_to_float(vnorm),
                normalized_unit=_clean_str(nunit),
                unit=_clean_str(unit),
                value_raw=_clean_str(vraw),
                domain=_clean_str(domain),
                doc_id=_clean_str(doc_id),
                page=_to_int(page),
                material=_clean_str(mat_name),
            )
        )
    return out


# ------------------------------------------------------- property-id resolution
_VOCAB = None


def _property_id(property_name: str | None) -> str | None:
    """Map a graph ``property_name`` to a canonical ``prop:*`` id (§6.6/§7.7)."""
    if not property_name:
        return None
    global _VOCAB
    if _VOCAB is None:
        from kg_extractors.property_vocab import load_property_vocab

        _VOCAB = load_property_vocab()
    hit = _VOCAB.canonical_for(property_name)
    if hit:
        return hit
    return f"prop:{property_name.strip().lower()}"


def _value_token(row: _Row) -> str:
    """Reconstruct a value+unit string for the ambiguity detector.

    Prefer the raw extraction string (``"2.5 %"``); fall back to the stored
    numeric value with its raw or normalized unit token.
    """
    if row.value_raw:
        return row.value_raw
    unit = row.unit or row.normalized_unit or ""
    if row.value_normalized is not None:
        return f"{row.value_normalized} {unit}".strip()
    return unit


def _classify_row(row: _Row) -> UnitReviewTask | None:
    """Diagnose one measurement; return a review task or ``None`` (clean).

    Ambiguity is checked first (a bare ``%`` still carries a magnitude), then
    the missing-unit gap. Both reuse the already-built §7.6 detectors.
    """
    ctx = row.property_name
    pid = _property_id(row.property_name)

    # 1. ambiguous_unit — bare %/ppm without a basis in a composition context.
    flag = detect_ambiguous_unit(_value_token(row), ctx)
    if flag is not None:
        return UnitReviewTask(
            id=row.id,
            kind=KIND_AMBIGUOUS,
            kind_ru=_KIND_LABEL_RU[KIND_AMBIGUOUS],
            name=row.name,
            property_name=row.property_name,
            property_id=pid,
            material=row.material,
            domain=row.domain,
            value=row.value_normalized,
            value_raw=row.value_raw,
            unit=flag.unit,
            candidates=list(flag.candidates),
            reason=flag.reason,
            gap_type=KIND_AMBIGUOUS,
            doc_id=row.doc_id,
            page=row.page,
        )

    # 2. missing_unit — value present, expected unit absent (policy-aware).
    unit_token = row.unit or row.normalized_unit
    if row.value_normalized is not None and not (unit_token and unit_token.strip()):
        report = classify_problems(row.value_normalized, unit_token, property_id=pid)
        if report.is_missing_unit_gap:
            return UnitReviewTask(
                id=row.id,
                kind=KIND_MISSING,
                kind_ru=_KIND_LABEL_RU[KIND_MISSING],
                name=row.name,
                property_name=row.property_name,
                property_id=pid,
                material=row.material,
                domain=row.domain,
                value=row.value_normalized,
                value_raw=row.value_raw,
                unit=None,
                candidates=[],
                reason=_MISSING_REASON,
                gap_type=KIND_MISSING,
                doc_id=row.doc_id,
                page=row.page,
            )
    return None


def _sort_key(t: UnitReviewTask) -> tuple[int, str]:
    return (_KIND_RANK.get(t.kind, 0), t.id)


# ------------------------------------------------------------------- endpoints
@router.get("/queue", response_model=QueueResponse)
def queue(limit: int = 4000, kind: str | None = None, domain: str | None = None) -> QueueResponse:
    """Review queue of §7.6 unit problems + the gap matrix for Карта пробелов.

    Scans up to *limit* ``Measurement`` nodes, reuses the ambiguous-unit and
    missing-unit detectors, and returns only the flagged ones (optionally
    filtered by *kind* / *domain*), most-actionable first, with per-kind counts
    and a ``{kind: {domain: count}}`` gap matrix.
    """
    store = get_store()
    rows = _scan_rows(store, limit)

    tasks: list[UnitReviewTask] = []
    for row in rows:
        task = _classify_row(row)
        if task is not None:
            tasks.append(task)

    if kind:
        tasks = [t for t in tasks if t.kind == kind]
    if domain:
        tasks = [t for t in tasks if t.domain == domain]

    tasks.sort(key=_sort_key, reverse=True)

    counts: dict[str, int] = {KIND_AMBIGUOUS: 0, KIND_MISSING: 0}
    gap_matrix: dict[str, dict[str, int]] = {}
    for t in tasks:
        counts[t.kind] = counts.get(t.kind, 0) + 1
        dom = t.domain or "?"
        gap_matrix.setdefault(t.gap_type, {})
        gap_matrix[t.gap_type][dom] = gap_matrix[t.gap_type].get(dom, 0) + 1

    return QueueResponse(
        total_measurements=len(rows),
        flagged=len(tasks),
        counts=counts,
        gap_matrix=gap_matrix,
        tasks=tasks,
    )


@router.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest) -> ExplainResponse:
    """Pure-compute §7.6 verdict for an ad-hoc value (no graph, no LLM).

    Mirrors the acceptance criterion: ``"2.5 %"`` + ``composition`` yields
    ``unit_ambiguous`` with candidates ``wt%`` / ``at%`` / ``vol%`` (never a
    silent pick); a bare ``"320"`` yields the ``missing_unit`` gap. Lets the UI
    demonstrate the honest behaviour without touching stored data.
    """
    value_str = req.value_raw if req.value_raw is not None else ""
    if req.unit:
        value_str = f"{value_str} {req.unit}".strip()

    flag = detect_ambiguous_unit(value_str, req.property_context)
    if flag is not None:
        return ExplainResponse(
            kind=KIND_AMBIGUOUS,
            kind_ru=_KIND_LABEL_RU[KIND_AMBIGUOUS],
            unit_ambiguous=True,
            unit_missing=False,
            candidates=list(flag.candidates),
            reason=flag.reason,
            is_missing_unit_gap=False,
            review_task=flag.as_dict(),
        )

    pid = _property_id(req.property_context)
    numeric = _to_float(req.value_raw)
    report = classify_problems(numeric if numeric is not None else req.value_raw, req.unit,
                               property_id=pid)
    if report.is_missing_unit_gap:
        return ExplainResponse(
            kind=KIND_MISSING,
            kind_ru=_KIND_LABEL_RU[KIND_MISSING],
            unit_ambiguous=False,
            unit_missing=True,
            candidates=[],
            reason=_MISSING_REASON,
            is_missing_unit_gap=True,
            review_task=report.review_task,
        )

    return ExplainResponse(
        kind=None,
        kind_ru=None,
        unit_ambiguous=False,
        unit_missing=False,
        candidates=[],
        reason="единица однозначна — review не требуется",
        is_missing_unit_gap=False,
        review_task=report.review_task,
    )
