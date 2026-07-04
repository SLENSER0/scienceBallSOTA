"""§25.14/§25.13 — absence-verdict annotation for the «карта неизвестного» UI.

The absence layer (§25) already builds a (material × property) coverage grid and
can classify any single cell, but the flat gaps list surfaced to the UI hides all
of that. This router joins the two: it walks the real coverage grid and asks the
sharper §25.11/§25.13 question of every *not-covered* cell — *is this a genuine
absence, a likely extraction miss, a retraction, or an undecidable case?* — by
reusing the already-built modules, without writing a line of new absence math:

- :func:`kg_retrievers.absence_map.build_absence_map` enumerates the grid and marks
  which cells are covered vs empty;
- :func:`kg_retrievers.absence_signals.classify_cell` fuses the three signals
  (active observations / retracted observations / MENTIONS-without-observation)
  of each empty cell into a verdict plus the Bayesian posteriors
  ``p_truly_absent`` / ``p_extractor_missed``;
- :func:`kg_retrievers.absence_rationale.build_rationale` turns that into a stable
  RU headline + ordered factor strings (MENTIONS, recall context, retraction
  state, extractor-miss threshold) and carries the ``calibrated`` badge.

Strictly **read-only** — never mutates the graph (unlike ``POST /gaps/scan``).
``calibrated`` is reported honestly: the live classifier runs on the heuristic
default recall prior (no gold calibration set is loaded), so
``absence_meta.calibrated`` is ``False`` / ``method="heuristic"``. A distinct
``/gaps/absence`` path under the existing ``/gaps`` prefix; no collision with the
flat ``gaps.py`` handlers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["gaps"])

# RU verdict labels shown as chips in the §25.14 UI. Kept server-side too so the
# API is self-describing (the frontend keeps its own copy for rendering).
_VERDICT_RU: dict[str, str] = {
    "genuine_gap": "реальный пробел",
    "possible_miss": "возможно пропуск извлечения",
    "retracted": "ретрагировано",
    "abstain": "неопределённо",
    "present": "покрыто",
    "covered": "покрыто (без значения)",
}

# Verdicts that must NOT read as an ordinary «белый пробел» in the UI (§25.14).
_NON_WHITE = frozenset({"possible_miss", "retracted", "abstain"})

# Covered statuses in the absence map — not gaps, skipped before classification.
_COVERED_STATUS = "covered"


def _classify_cell(
    store: Any,
    material_id: str,
    material_name: str | None,
    property_name: str,
    domain: str | None,
) -> dict[str, Any]:
    """Classify one (material, property) cell into a full §25.14 verdict payload."""
    from kg_retrievers.absence_rationale import build_rationale
    from kg_retrievers.absence_signals import classify_cell

    sig = classify_cell(store, material_id, property_name)
    signals = sig.signals
    # No gold-calibrated recall prior is loaded on the live profile → heuristic.
    calibrated = False
    rationale = build_rationale(
        {
            "verdict": sig.verdict,
            "p_extractor_missed": sig.p_extractor_missed,
            "has_mentions": bool(signals.get("mentioned_without_observation")),
            "recall": float(signals.get("recall_prior", 0.0)),
            "retracted_count": int(signals.get("retracted_observations", 0)),
            "calibrated": calibrated,
        }
    )

    return {
        "gap_id": f"absence:{material_id}:{property_name}",
        "material_id": material_id,
        "material_name": material_name or material_id,
        "property_name": property_name,
        "domain": domain,
        "absence_verdict": sig.verdict,
        "verdict_ru": _VERDICT_RU.get(sig.verdict, sig.verdict),
        "p_truly_absent": sig.p_truly_absent,
        "p_extractor_missed": sig.p_extractor_missed,
        # «риск пропуска извлечения N%» — integer percent for the card.
        "extractor_miss_risk_pct": round(sig.p_extractor_missed * 100),
        "is_genuine_gap": sig.verdict == "genuine_gap",
        # possible_miss / retracted / abstain must not render as a plain white gap.
        "non_white_gap": sig.verdict in _NON_WHITE,
        "absence_meta": {
            "calibrated": calibrated,
            "method": "heuristic",
            "recall_prior": signals.get("recall_prior"),
        },
        "signals": {
            "active_observations": signals.get("active_observations", 0),
            "retracted_observations": signals.get("retracted_observations", 0),
            "mentioned_without_observation": bool(
                signals.get("mentioned_without_observation")
            ),
        },
        "rationale": rationale.as_dict(),
    }


@router.get("/gaps/absence")
def gaps_absence(
    domain: str | None = Query(None, description="Filter by the material's domain"),
    verdict: str | None = Query(None, description="Keep only this absence_verdict"),
    limit: int = Query(120, ge=1, le=400, description="Max cells to classify"),
) -> dict:
    """Absence-verdict annotated gaps for the «карта неизвестного» UI (§25.14/§25.13).

    Walks the real (material × property) coverage grid, classifies every *empty*
    cell via the §25.11 fused signals, and returns each with ``absence_verdict``,
    both Bayesian posteriors, the extractor-miss risk percent, the
    calibrated/heuristic ``absence_meta`` badge, and a RU rationale — plus a
    ``by_verdict`` summary for the filter/legend. Read-only: never mutates the graph.
    """
    from kg_retrievers.absence_map import build_absence_map

    store = get_store()
    amap = build_absence_map(store, domain=domain)

    annotated: list[dict[str, Any]] = []
    for cell in amap.cells:
        if getattr(cell, "status", "") == _COVERED_STATUS:
            continue  # covered cells are not gaps
        mat_nd = store.get_node(cell.material_id) or {}
        cell_domain = mat_nd.get("domain")
        item = _classify_cell(
            store,
            cell.material_id,
            getattr(cell, "material_name", None),
            cell.property_name,
            cell_domain,
        )
        if verdict and item["absence_verdict"] != verdict:
            continue
        annotated.append(item)
        if len(annotated) >= limit:
            break

    # Default order: highest extractor-miss risk first (most actionable to re-check).
    annotated.sort(key=lambda a: a["p_extractor_missed"], reverse=True)

    by_verdict: dict[str, int] = {}
    for a in annotated:
        v = a["absence_verdict"]
        by_verdict[v] = by_verdict.get(v, 0) + 1

    return {
        "count": len(annotated),
        "by_verdict": by_verdict,
        "verdict_labels": _VERDICT_RU,
        "calibrated": False,
        "gaps": annotated,
    }
