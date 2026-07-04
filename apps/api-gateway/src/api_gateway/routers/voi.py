"""§25.11 — Value-of-Information ranking of the «карта неизвестного».

The absence layer (§25) already builds a (material × property) coverage grid and,
for every empty cell, fuses three signals into the Bayesian posterior
``p_extractor_missed`` — the probability the observed absence is an *extraction
miss* rather than a real absence. That number answers *how likely is this a miss?*
but not the sharper R&D question: *which unknown measurement, if we ran it, would
strip out the most uncertainty?*

This router answers exactly that by chaining two already-built modules — it writes
no new absence math and no new ranking math:

- :func:`kg_retrievers.absence_map.build_absence_map` enumerates the grid and marks
  which cells are covered vs empty;
- :func:`kg_retrievers.absence_signals.classify_cell` gives each empty cell its
  ``p_extractor_missed`` posterior;
- :func:`kg_retrievers.absence_value_of_information.rank_value_of_information` scores
  each cell by the binary Shannon entropy ``H(p_extractor_missed)`` — the value of
  information. VoI peaks at ``1.0`` bit when ``p = 0.5`` (maximally ambiguous: the
  measurement that most reduces uncertainty) and falls to ``0.0`` at the certain
  ends. Ranking by VoI tells an R&D lead *where to put the next experiment*.

Note this is a different question from the flat extractor-miss risk sort used by
``/gaps/absence`` (§25.14): a cell with ``p = 0.95`` has high miss-risk but *low*
VoI — we are already fairly sure, so measuring it teaches us little. VoI surfaces
the genuinely ambiguous cells instead.

Strictly **read-only** — never mutates the graph. Exposed as
``/absence/value-of-information``. It deliberately does *not* nest under ``/gaps``:
``gaps.py`` registers a greedy ``GET /gaps/{gap_id}`` that shadows any sibling
``/gaps/<literal>`` path declared in a later-registered router (the live cause of
``/gaps/absence`` returning ``gap not found``). Sitting under ``/absence`` makes
this route immune to router registration order.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["gaps"])

# RU verdict labels, kept server-side so the API is self-describing (the frontend
# holds its own rendering copy). Mirrors absence.py so both surfaces stay aligned.
_VERDICT_RU: dict[str, str] = {
    "genuine_gap": "реальный пробел",
    "possible_miss": "возможно пропуск извлечения",
    "retracted": "ретрагировано",
    "abstain": "неопределённо",
    "present": "покрыто",
    "covered": "покрыто (без значения)",
}

# Covered statuses in the absence map — not gaps, skipped before classification.
_COVERED_STATUS = "covered"


@router.get("/absence/value-of-information")
def gaps_value_of_information(
    domain: str | None = Query(None, description="Filter by the material's domain"),
    top_n: int = Query(10, ge=1, le=100, description="Size of the ranked shortlist"),
    scan_limit: int = Query(
        400, ge=1, le=2000, description="Max empty cells to classify before ranking"
    ),
) -> dict:
    """Rank unknown (material × property) measurements by value of information (§25.11).

    Walks the real coverage grid, classifies every *empty* cell to obtain its
    ``p_extractor_missed`` posterior, and scores each by the binary-entropy value of
    information ``H(p_extractor_missed)``. Returns the full ranked list plus a
    ``top`` shortlist and the single highest-VoI ``recommended_experiment`` — the
    measurement that would most reduce the map's uncertainty. Read-only.
    """
    from kg_retrievers.absence_map import build_absence_map
    from kg_retrievers.absence_signals import classify_cell
    from kg_retrievers.absence_value_of_information import (
        SCHEMA_VERSION,
        rank_value_of_information,
    )

    store = get_store()
    amap = build_absence_map(store, domain=domain)

    # Carry display context (name, verdict) keyed by (material, property) so we can
    # re-join it onto the ranked VoICells, which only keep the ids + scores.
    context: dict[tuple[str, str], dict[str, Any]] = {}
    cells: list[dict[str, Any]] = []
    for cell in amap.cells:
        if getattr(cell, "status", "") == _COVERED_STATUS:
            continue  # covered cells are known — no information to gain
        sig = classify_cell(store, cell.material_id, cell.property_name)
        key = (cell.material_id, cell.property_name)
        context[key] = {
            "material_name": getattr(cell, "material_name", None) or cell.material_id,
            "absence_verdict": sig.verdict,
            "verdict_ru": _VERDICT_RU.get(sig.verdict, sig.verdict),
            "p_truly_absent": sig.p_truly_absent,
        }
        cells.append(
            {
                "material_id": cell.material_id,
                "property_name": cell.property_name,
                "p_extractor_missed": sig.p_extractor_missed,
            }
        )
        if len(cells) >= scan_limit:
            break

    report = rank_value_of_information(cells, top_n=top_n)

    def _enrich(voi_cell: Any) -> dict[str, Any]:
        key = (voi_cell.material_id, voi_cell.property_name)
        ctx = context.get(key, {})
        return {
            "material_id": voi_cell.material_id,
            "material_name": ctx.get("material_name", voi_cell.material_id),
            "property_name": voi_cell.property_name,
            "p_extractor_missed": voi_cell.p_missed,
            "voi": voi_cell.voi,
            # VoI is already a 0..1-bit entropy; expose an integer percent for bars.
            "voi_pct": round(voi_cell.voi * 100),
            "absence_verdict": ctx.get("absence_verdict"),
            "verdict_ru": ctx.get("verdict_ru"),
            "p_truly_absent": ctx.get("p_truly_absent"),
        }

    ranked = [_enrich(c) for c in report.cells]
    top = [_enrich(c) for c in report.top]
    recommended = top[0] if top else None

    return {
        "schema_version": SCHEMA_VERSION,
        "scanned": len(cells),
        "total_voi": report.total_voi,
        "verdict_labels": _VERDICT_RU,
        "recommended_experiment": recommended,
        "top": top,
        "cells": ranked,
    }
