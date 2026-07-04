"""Evidential arbiter — какое измерение вероятно верное и почему (§15.4).

The agentic arbiter (:mod:`agent_service.contradiction_analysis`, ``/api/v1/arbiter``)
returns an LLM verdict; :mod:`api_gateway.routers.arbiter_resolve` commits a human choice.
This router fills the third seat: a **deterministic, evidential** arbitration that makes the
call *provable rather than assertive* — it ranks each conflicting side by its source quality
(``evidence_strength`` → ``review_status`` → ``confidence`` → OCR) and lays the sides'
confidence intervals on one axis so the UI can render **непересечение доверительных
интервалов** as the visual proof of a genuine conflict.

Endpoints (read-only, no graph mutation, no LLM call — stable & offline-safe):

* ``GET /api/v1/arbiter-evidence/contradictions`` — the flagged contradictions with the
  spread of their conflicting values (reuses ``agent_service.contradiction_analysis``).
* ``GET /api/v1/arbiter-evidence/{cid}`` — the evidential arbitration payload: every side
  with its source-quality breakdown + confidence interval, the ``likely_correct`` side, the
  ``§15.4`` contradiction subtype/severity/reasons, and the interval-axis geometry (per-side
  bars + pairwise disjointness) for the non-overlap visualization.

Pure reuse — nothing is re-implemented here:

* :func:`kg_retrievers.contradiction_detector.detect_contradiction` / ``EVIDENCE_RANK`` — the
  §15.4 heuristics (numeric divergence / disjoint CIs / effect direction) and the provenance
  ranking that decides the likely-correct side.
* :func:`kg_common.units.comparison.intervals_overlap` — the closed-interval overlap test that
  drives the «пересекаются / не пересекаются» flag.
* :func:`agent_service.contradiction_analysis.list_contradictions` — the list surface.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/arbiter-evidence", tags=["contradictions"])

# One row per conflicting Measurement of the contradiction. Only *schema-guaranteed*
# properties are projected here — the embedded Kuzu store binds column names strictly,
# so optional CI / OCR fields (which no seed node carries) are read per-node from
# :meth:`get_node` instead, where a missing key degrades to ``None`` on both backends.
# Evidence / Paper provenance is collected and coalesced in Python.
_SIDES_CYPHER = (
    "MATCH (c:Node {id:$cid})-[:Rel]-(m:Node {label:'Measurement'}) "
    "OPTIONAL MATCH (m)-[:Rel]-(e:Node {label:'Evidence'}) "
    "OPTIONAL MATCH (m)-[:Rel]-(p:Node {label:'Paper'}) "
    "RETURN m.id AS mid, m.value_normalized AS val, m.normalized_unit AS unit, "
    "m.property_name AS prop, m.confidence AS conf, m.review_status AS review, "
    "m.evidence_strength AS strength, "
    "m.country AS country, m.practice_type AS practice, "
    "collect(DISTINCT e.text) AS texts, count(DISTINCT e) AS ev_count, "
    "collect(DISTINCT e.evidence_strength) AS e_strengths, "
    "collect(DISTINCT e.review_status) AS e_reviews, "
    "collect(DISTINCT p.evidence_strength) AS p_strengths "
    "ORDER BY mid LIMIT 12"
)


def _first(seq: Any) -> Any:
    """First non-null element of a ``collect(...)`` list (backend index-base agnostic)."""
    if isinstance(seq, (list, tuple)):
        return next((v for v in seq if v is not None), None)
    return seq

# review_status → quality component in [0, 1] (§15.4 «сравнивать review_status»).
_REVIEW_QUALITY: dict[str, float] = {
    "accepted": 1.0,
    "verified": 1.0,
    "approved": 1.0,
    "resolved": 0.9,
    "pending": 0.5,
    "in_review": 0.5,
    "unreviewed": 0.4,
    "auto": 0.4,
    "flagged": 0.2,
    "rejected": 0.0,
    "dismissed": 0.0,
}

# Weights of the four provenance signals in the blended source-quality score
# (§15.4). Evidence strength dominates — it is the provenance ordering the §15.4
# heuristic itself uses — then curation review, then extractor confidence, then OCR.
_W_STRENGTH, _W_REVIEW, _W_CONF, _W_OCR = 0.40, 0.25, 0.20, 0.15


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _strength_quality(strength: str | None) -> tuple[float, int]:
    """Map an ``evidence_strength`` token to (quality in [0,1], raw EVIDENCE_RANK)."""
    from kg_retrievers.contradiction_detector import EVIDENCE_RANK

    rank = EVIDENCE_RANK.get(str(strength or "").strip().lower(), 0)
    top = max(EVIDENCE_RANK.values()) or 1
    return round(rank / top, 4), rank


def _review_quality(review: str | None) -> float:
    return _REVIEW_QUALITY.get(str(review or "").strip().lower(), 0.4)


def _ocr_quality(ocr_q: Any, ocr_c: Any) -> tuple[float, bool]:
    """OCR-quality component in [0,1]; second value flags whether OCR data existed.

    Absent OCR fields are treated as clean digital text (quality 1.0) — the §15.4
    heuristic only *penalises* a measurement when OCR is present and poor.
    """
    for raw in (ocr_q, ocr_c):
        v = _as_float(raw)
        if v is not None:
            return round(max(0.0, min(v, 1.0)), 4), True
    return 1.0, False


def _interval(row: dict[str, Any]) -> tuple[float | None, float | None, str]:
    """Derive a confidence interval [lo, hi] for a side and label its provenance.

    Preference order (§15.4 «value ± std / value_min..value_max»): explicit CI →
    value ± std → [value_min, value_max] → degenerate point interval at the value.
    """
    val = _as_float(row.get("val"))
    lo, hi = _as_float(row.get("ci_low")), _as_float(row.get("ci_high"))
    if lo is not None and hi is not None:
        return (min(lo, hi), max(lo, hi), "ci")
    std = _as_float(row.get("std"))
    if val is not None and std is not None and std > 0:
        return (val - abs(std), val + abs(std), "std")
    vmin, vmax = _as_float(row.get("vmin")), _as_float(row.get("vmax"))
    if vmin is not None and vmax is not None:
        return (min(vmin, vmax), max(vmin, vmax), "minmax")
    if val is not None:
        return (val, val, "point")
    return (None, None, "none")


def _enrich_optional(store: Any, mid: str, row: dict[str, Any]) -> None:
    """Fold optional interval / OCR fields from the node map into ``row`` (schema-safe)."""
    node = store.get_node(mid) or {}
    row["ci_low"] = node.get("ci_low")
    row["ci_high"] = node.get("ci_high")
    row["std"] = node.get("value_std") or node.get("std")
    row["vmin"] = node.get("value_min")
    row["vmax"] = node.get("value_max")
    row["ocr_q"] = node.get("ocr_quality")
    row["ocr_c"] = node.get("ocr_confidence")
    row["year"] = node.get("source_year") or node.get("year")


def _load_sides(store: Any, cid: str) -> list[dict[str, Any]]:
    """Load the conflicting sides with a per-side source-quality breakdown + interval."""
    cols = (
        "mid", "val", "unit", "prop", "conf", "review", "strength",
        "country", "practice", "texts", "ev_count",
        "e_strengths", "e_reviews", "p_strengths",
    )
    sides: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in store.rows(_SIDES_CYPHER, {"cid": cid}):
        row = dict(zip(cols, r, strict=False))
        mid = row.get("mid")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        _enrich_optional(store, mid, row)

        text = _first(row.get("texts"))
        strength = (
            row.get("strength") or _first(row.get("e_strengths")) or _first(row.get("p_strengths"))
        )
        review = row.get("review") or _first(row.get("e_reviews"))
        conf = _as_float(row.get("conf"))
        conf_q = round(max(0.0, min(conf, 1.0)), 4) if conf is not None else 0.5

        s_q, s_rank = _strength_quality(strength)
        r_q = _review_quality(review)
        o_q, o_present = _ocr_quality(row.get("ocr_q"), row.get("ocr_c"))
        quality = round(
            _W_STRENGTH * s_q + _W_REVIEW * r_q + _W_CONF * conf_q + _W_OCR * o_q, 4
        )

        lo, hi, ci_src = _interval(row)
        sides.append(
            {
                "claim_id": mid,
                "value": _as_float(row.get("val")),
                "unit": row.get("unit"),
                "property": row.get("prop"),
                "confidence": conf,
                "review_status": review,
                "evidence_strength": strength,
                "evidence_rank": s_rank,
                "ocr_quality": o_q if o_present else None,
                "year": row.get("year"),
                "country": row.get("country"),
                "practice": row.get("practice"),
                "evidence": (text or "")[:280] or None,
                "evidence_count": row.get("ev_count") or 0,
                "ci_low": lo,
                "ci_high": hi,
                "ci_source": ci_src,
                "quality": {
                    "strength": s_q,
                    "review": r_q,
                    "confidence": conf_q,
                    "ocr": o_q,
                    "score": quality,
                },
                "quality_score": quality,
            }
        )
    return sides


def _detector_measurement(side: dict[str, Any]) -> dict[str, Any]:
    """Adapt a side into the dict shape :func:`detect_contradiction` expects.

    A *real* interval (``ci`` / ``std`` / ``minmax``) is forwarded so the detector
    can fire its ``ci_disjoint`` heuristic; a degenerate ``point`` interval is not,
    so a plain gap between point estimates reads as ``numeric_divergence`` instead.
    """
    real_ci = side.get("ci_source") in ("ci", "std", "minmax")
    return {
        "value_normalized": side.get("value"),
        "normalized_unit": side.get("unit"),
        "confidence": side.get("confidence"),
        "evidence_strength": side.get("evidence_strength"),
        "ci_low": side.get("ci_low") if real_ci else None,
        "ci_high": side.get("ci_high") if real_ci else None,
    }


def _verdict_basis(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Name the signal that separated the two best sides (for an honest UI caption)."""
    if a.get("evidence_rank") != b.get("evidence_rank"):
        return "evidence_strength"
    ra, rb = a["quality"]["review"], b["quality"]["review"]
    if ra != rb:
        return "review_status"
    ca, cb = a.get("confidence"), b.get("confidence")
    if ca is not None and cb is not None and ca != cb:
        return "confidence"
    if a["quality"]["ocr"] != b["quality"]["ocr"]:
        return "ocr_quality"
    if a["quality_score"] != b["quality_score"]:
        return "source_quality"
    return "tie"


def _intervals_payload(sides: list[dict[str, Any]]) -> dict[str, Any]:
    """Axis geometry + pairwise overlap flags for the non-overlap visualization."""
    from kg_common.units.comparison import intervals_overlap

    bounded = [
        s for s in sides if s.get("ci_low") is not None and s.get("ci_high") is not None
    ]
    axis_min = min((s["ci_low"] for s in bounded), default=None)
    axis_max = max((s["ci_high"] for s in bounded), default=None)

    pairs: list[dict[str, Any]] = []
    disjoint_any = False
    for i in range(len(bounded)):
        for j in range(i + 1, len(bounded)):
            a, b = bounded[i], bounded[j]
            overlap = intervals_overlap(
                (a["ci_low"], a["ci_high"]), (b["ci_low"], b["ci_high"])
            )
            disjoint_any = disjoint_any or not overlap
            pairs.append(
                {
                    "a": a["claim_id"],
                    "b": b["claim_id"],
                    "overlap": overlap,
                    "disjoint": not overlap,
                }
            )
    return {
        "axis_min": axis_min,
        "axis_max": axis_max,
        "unit": next((s.get("unit") for s in bounded if s.get("unit")), None),
        "pairs": pairs,
        "any_disjoint": disjoint_any,
    }


def _require_contradiction(store: Any, cid: str) -> dict[str, Any]:
    node = store.get_node(cid)
    if node is None or node.get("label") != "Contradiction":
        raise HTTPException(status_code=404, detail="contradiction not found")
    return node


@router.get("/contradictions")
def contradictions(limit: int = 40, _role: str = Depends(current_role)) -> dict[str, Any]:
    """List flagged contradictions with the spread of their conflicting values."""
    from agent_service.contradiction_analysis import list_contradictions

    return {"contradictions": list_contradictions(get_store(), limit=limit)}


@router.get("/{cid:path}")
def arbitrate(cid: str, _role: str = Depends(current_role)) -> dict[str, Any]:
    """Evidential arbitration for one contradiction (§15.4).

    Ranks the conflicting sides by blended source quality, names the
    ``likely_correct`` side, runs the §15.4 heuristics for subtype/severity/reasons,
    and returns the interval-axis geometry so the UI can prove or disprove a genuine
    conflict by whether the confidence intervals overlap.
    """
    from kg_retrievers.contradiction_detector import detect_contradiction

    store = get_store()
    node = _require_contradiction(store, cid)
    sides = _load_sides(store, cid)
    if len(sides) < 2:
        return {
            "id": cid,
            "name": node.get("name") or cid,
            "status": node.get("review_status"),
            "sides": sides,
            "likely_correct_id": None,
            "verdict_basis": "insufficient",
            "subtype": "none",
            "severity": 0.0,
            "reasons": [],
            "intervals": _intervals_payload(sides),
            "note": "недостаточно сопоставимых сторон для арбитража",
        }

    # Rank by blended source quality; stable tie-break on evidence count then id.
    ranked = sorted(
        sides,
        key=lambda s: (s["quality_score"], s.get("evidence_count", 0), s["claim_id"]),
        reverse=True,
    )
    for i, s in enumerate(ranked):
        s["rank"] = i + 1
        s["likely_correct"] = False
    best, runner = ranked[0], ranked[1]
    winner_id = best["claim_id"] if best["quality_score"] > runner["quality_score"] else None
    if winner_id is None:
        # Quality tie — fall back to the §15.4 detector's provenance call on the pair.
        verdict_ab = detect_contradiction(
            _detector_measurement(best), _detector_measurement(runner)
        )
        if verdict_ab.likely_correct == "a":
            winner_id = best["claim_id"]
        elif verdict_ab.likely_correct == "b":
            winner_id = runner["claim_id"]
    if winner_id:
        for s in ranked:
            s["likely_correct"] = s["claim_id"] == winner_id

    # §15.4 subtype / severity / reasons from the two strongest-diverging sides.
    verdict = detect_contradiction(
        _detector_measurement(best), _detector_measurement(runner)
    )

    return {
        "id": cid,
        "name": node.get("name") or cid,
        "status": node.get("review_status"),
        "property": best.get("property"),
        "unit": best.get("unit"),
        "sides": ranked,
        "likely_correct_id": winner_id,
        "verdict_basis": _verdict_basis(best, runner) if winner_id else "tie",
        "subtype": verdict.subtype,
        "severity": verdict.severity,
        "reasons": list(verdict.reasons),
        "intervals": _intervals_payload(ranked),
    }
