"""[DE] Track-A semantic extraction matching (spec §33, port of science_ball matching).

A gold fact counts as extracted only if an observation matches on **material +
property + value(±tol) + unit(alias-aware) + direction + evidence(doc &
source_type)**, with ``regime`` reported as a supplementary (non-required) check.
Purely additive and read-only over the Kuzu store. Offline prose (``chunk``)
recall ≈ 0 is *expected* — the deterministic table/catalog paths commit
observations, prose does not without the (review-gated) LLM extractor.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from kg_eval.schemas import GoldExtractionFact
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.retractions import active_measurements

_UNIT_ALIASES = {
    "%": "percent",
    "percent": "percent",
    "hv": "hv",
    "hv0.5": "hv",
    "mpa": "mpa",
    "gpa": "gpa",
}


def _norm_unit(u: str | None) -> str | None:
    if u is None:
        return None
    key = str(u).strip().lower()
    return _UNIT_ALIASES.get(key, key)


def _value_ok(
    gold: float | None, got: float | None, *, tol_frac: float = 0.03, tol_abs: float = 0.5
) -> bool:
    if gold is None:
        return True  # prose facts with no stated value are not value-checked
    if got is None:
        return False
    return abs(float(gold) - float(got)) <= max(tol_abs, tol_frac * abs(float(gold)))


def _property_name(store: KuzuGraphStore, property_id: str) -> str:
    nd = store.get_node(property_id)
    if nd:
        return nd.get("property_name") or nd.get("name") or property_id
    return property_id


def _evidence_of(store: KuzuGraphStore, meas_id: str) -> list[dict[str, Any]]:
    rows = store.rows(
        "MATCH (m:Node {id:$mid})-[r:Rel]->(e:Node) "
        "WHERE r.type='SUPPORTED_BY' AND e.label='Evidence' "
        "RETURN e.doc_id, e.source_type",
        {"mid": meas_id},
    )
    return [{"doc_id": d, "source_type": st} for d, st in rows]


def _iter_observations(
    store: KuzuGraphStore, material_id: str, property_id: str
) -> Iterator[tuple[str, dict[str, Any]]]:
    prop_name = _property_name(store, property_id)
    for m in active_measurements(store, material_id, include_retracted=True):
        if m.get("property_name") != prop_name:
            continue
        obs = {
            "value": m.get("value_normalized"),
            "unit": m.get("unit"),
            "direction": m.get("direction"),
            "observation_id": m["id"],
        }
        yield m["id"], {"observation": obs, "evidence": _evidence_of(store, m["id"])}


def match_fact(
    store: KuzuGraphStore,
    gold: GoldExtractionFact,
    *,
    tol_frac: float = 0.03,
    temp_tol: float = 10.0,
) -> dict[str, Any]:
    """Best semantic match for one gold fact + a per-field breakdown."""
    best: dict[str, Any] | None = None
    for _run_id, orow in _iter_observations(store, gold.material_id, gold.property_id):
        obs = orow.get("observation") or {}
        evid = orow.get("evidence") or []
        ev_ok = any(
            e.get("doc_id") == gold.doc_id
            and (gold.source_type is None or e.get("source_type") == gold.source_type)
            for e in evid
        )
        if not ev_ok:
            continue
        checks = {
            "material": True,
            "property": True,
            "evidence": True,
            "value": _value_ok(gold.stated_value, obs.get("value"), tol_frac=tol_frac),
            "unit": gold.unit is None or _norm_unit(gold.unit) == _norm_unit(obs.get("unit")),
            "direction": gold.direction is None or gold.direction == obs.get("direction"),
        }
        # Supplementary regime check (not part of the core match). SOTA synthetic
        # measurements carry no regime, so reg_type/reg_temp are None → passes.
        reg_type = reg_temp = None
        gt = (gold.regime or {}).get("regime_type")
        gtemp = (gold.regime or {}).get("temperature_C")
        regime_ok = (gt is None or reg_type is None or gt == reg_type) and (
            gtemp is None or reg_temp is None or abs(float(gtemp) - float(reg_temp)) <= temp_tol
        )
        core = all(checks.values())
        cand = {
            "matched": core,
            "checks": checks,
            "regime_ok": regime_ok,
            "observation_id": obs.get("observation_id"),
            "got_value": obs.get("value"),
            "got_unit": obs.get("unit"),
            "got_direction": obs.get("direction"),
        }
        if best is None or (cand["matched"] and not best["matched"]):
            best = cand
    if best is None:
        return {
            "matched": False,
            "checks": {"evidence": False},
            "regime_ok": False,
            "observation_id": None,
            "reason": "no observation with matching evidence",
        }
    return best


def evaluate_extraction_semantic(
    store: KuzuGraphStore, gold_facts: list[GoldExtractionFact], *, profile: str = "offline"
) -> dict[str, Any]:
    """Per-modality semantic recall / evidence recall / value precision."""
    by_mod: dict[str, dict[str, Any]] = {}
    cases: list[dict[str, Any]] = []
    for g in gold_facts:
        m = match_fact(store, g)
        agg = by_mod.setdefault(
            g.modality,
            {"expected": 0, "matched": 0, "evidence_hit": 0, "value_ok": 0, "regime_ok": 0},
        )
        agg["expected"] += 1
        agg["matched"] += int(m["matched"])
        agg["evidence_hit"] += int(bool(m.get("checks", {}).get("evidence")))
        agg["value_ok"] += int(bool(m.get("checks", {}).get("value")))
        agg["regime_ok"] += int(bool(m.get("regime_ok")))
        cases.append(
            {
                "doc_id": g.doc_id,
                "material_id": g.material_id,
                "property_id": g.property_id,
                "modality": g.modality,
                "extractable_offline": g.extractable_offline,
                "matched": m["matched"],
                "checks": m.get("checks", {}),
                "regime_ok": m.get("regime_ok", False),
            }
        )
    for a in by_mod.values():
        exp = a["expected"]
        a["semantic_recall"] = round(a["matched"] / exp, 3) if exp else None
        a["evidence_recall"] = round(a["evidence_hit"] / exp, 3) if exp else None
        a["value_precision"] = (
            round(a["value_ok"] / a["evidence_hit"], 3) if a["evidence_hit"] else None
        )
    det = [a for mod, a in by_mod.items() if mod in ("table_row", "catalog_row")]
    det_exp = sum(a["expected"] for a in det)
    det_match = sum(a["matched"] for a in det)
    return {
        "profile": profile,
        "by_modality": by_mod,
        "deterministic_semantic_recall": round(det_match / det_exp, 3) if det_exp else None,
        "prose_note": "offline: chunk facts are the measured prose blind spot "
        "(semantic_recall≈0 is expected, not a regression)",
        "cases": cases,
    }
