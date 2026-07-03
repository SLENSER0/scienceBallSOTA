"""[DE] Track-C benchmark — confidence-of-absence classification (spec §33.4/§33.5).

Scores the production absence layer (:func:`~kg_retrievers.absence_signals.
classify_cell`) and a ladder of baselines against the labelled synthetic corpus
(:mod:`kg_eval.datasets.synthetic`), turning the ``possible_miss`` vs
``genuine_gap`` decision into a measurable **classification**: a confusion matrix
(realities × verdicts), per-class precision/recall/F1, macro-F1, and the business
metrics that matter (``false_gap_rate``, ``miss_detection_recall``,
``false_possible_miss_rate``, ``no_data_recall``). ``abstain`` / ``covered`` are
never scored correct — they are counted as coverage.

The baselines all read the **same** graph signals and differ only in the decision
rule, so the leaderboard is a clean ablation:

    naive_graph  →  mentions_heuristic  →  static_modality  →  absence_confidence

On top, three *value methods* test the mention-vs-value fix:

    absence_confidence_value_oracle  — ground-truth ceiling (uses measurable_in_source)
    absence_confidence_value_regex   — the offline D1 regex over the mention prose
    absence_confidence_value_gate    — the REAL production gate (classify_cell value_gate=True)

Pure stdlib, fully offline. Calibration / bootstrap / Track-A live in sibling
modules and are attached by the orchestrator.
"""

from __future__ import annotations

from typing import Any

from kg_eval import calibration, guardrails, matching
from kg_eval.datasets.synthetic import build_synthetic
from kg_eval.schemas import REALITIES, VERDICTS, AbsencePrediction, DatasetManifest
from kg_retrievers.absence_signals import (
    GENUINE_GAP,
    POSSIBLE_MISS,
    PRESENT,
    classify_cell,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.value_in_mention import value_present_in_text

# Value methods intervene only on a possible_miss verdict, downgrading it to
# genuine_gap when the mentioning source states no measurable value.
VALUE_METHODS = (
    "absence_confidence_value_oracle",
    "absence_confidence_value_regex",
    "absence_confidence_value_gate",
)


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(x, nd)


def _rate(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


# -- signal extraction -----------------------------------------------------
def _signals(
    store: KuzuGraphStore, material_id: str, property_id: str, *, recall_prior: float
) -> dict[str, Any]:
    """The raw absence signals for one cell (gate OFF) — the shared baseline input."""
    sig = classify_cell(store, material_id, property_id, recall_prior=recall_prior)
    return {
        "active": sig.signals["active_observations"],
        "retracted": sig.signals["retracted_observations"],
        "mentioned": bool(sig.signals["mentioned_without_observation"]),
        "p_missed": sig.p_extractor_missed,
        "p_truly_absent": sig.p_truly_absent,
        "verdict": sig.verdict,
    }


# -- baseline / ablation ladder (signal dict -> verdict) -------------------
def _naive_graph(s: dict[str, Any]) -> str:
    """No observation ⇒ genuine_gap. Cannot express possible_miss / retracted."""
    return PRESENT if s["active"] > 0 else GENUINE_GAP


def _mentions_heuristic(s: dict[str, Any]) -> str:
    """Any mention ⇒ possible_miss. No recall model, no retracted class."""
    if s["active"] > 0:
        return PRESENT
    return POSSIBLE_MISS if s["mentioned"] else GENUINE_GAP


def _static_modality(s: dict[str, Any]) -> str:
    """Adds a lossy-modality cut (p_missed ≥ 0.5), still no retracted / abstain."""
    if s["active"] > 0:
        return PRESENT
    if s["mentioned"]:
        return POSSIBLE_MISS if s["p_missed"] >= 0.5 else GENUINE_GAP
    return GENUINE_GAP


BASELINES = {
    "naive_graph": _naive_graph,
    "mentions_heuristic": _mentions_heuristic,
    "static_modality": _static_modality,
}


# -- prediction dispatch ---------------------------------------------------
def _predictions(
    manifest: DatasetManifest,
    method: str,
    *,
    sigs: dict[str, dict[str, Any]],
    gate_verdicts: dict[str, str],
    calibrated: bool = False,
    mention_texts: dict[str, str] | None = None,
    aliases: dict[str, list[str]] | None = None,
) -> list[AbsencePrediction]:
    """Verdicts for every cell under ``method`` (a baseline, the current layer, or a
    value method), reusing per-cell signals computed once by the caller."""
    preds: list[AbsencePrediction] = []
    for cell in manifest.cells:
        s = sigs[cell.key()]
        if method in BASELINES:
            verdict = BASELINES[method](s)
        elif method == "absence_confidence_value_gate":
            verdict = gate_verdicts[cell.key()]  # the real production gate (graph value_present)
        elif method in VALUE_METHODS:
            verdict = s["verdict"]
            if verdict == POSSIBLE_MISS:
                if method == "absence_confidence_value_oracle":
                    downgrade = not cell.measurable_in_source  # ground-truth ceiling
                else:  # absence_confidence_value_regex
                    txt = (mention_texts or {}).get(cell.key())
                    als = (aliases or {}).get(cell.property_id, [])
                    # Finding D: downgrade only on POSITIVE evidence (text present).
                    downgrade = bool(txt) and not value_present_in_text(txt, als)
                if downgrade:
                    verdict = GENUINE_GAP
        else:  # "absence_confidence" / "absence_confidence_calibrated"
            verdict = s["verdict"]
        preds.append(
            AbsencePrediction(
                material_id=cell.material_id,
                property_id=cell.property_id,
                method=method,
                verdict=verdict,
                p_extractor_missed=s["p_missed"],
                p_truly_absent=s["p_truly_absent"],
                true_label=cell.true_label,
                calibrated=calibrated,
            )
        )
    return preds


# -- confusion matrix & per-class metrics ----------------------------------
def confusion_matrix(preds: list[AbsencePrediction]) -> dict[str, dict[str, int]]:
    """REALITIES rows × VERDICTS columns (``abstain`` / ``covered`` are columns only)."""
    m = {r: dict.fromkeys(VERDICTS, 0) for r in REALITIES}
    for p in preds:
        if p.true_label in m and p.verdict in m[p.true_label]:
            m[p.true_label][p.verdict] += 1
    return m


def per_class_prf(preds: list[AbsencePrediction]) -> dict[str, dict[str, Any]]:
    """One-vs-rest precision / recall / F1 / support per reality class."""
    out: dict[str, dict[str, Any]] = {}
    for c in REALITIES:
        tp = sum(1 for p in preds if p.true_label == c and p.verdict == c)
        fp = sum(1 for p in preds if p.true_label != c and p.verdict == c)
        fn = sum(1 for p in preds if p.true_label == c and p.verdict != c)
        support = sum(1 for p in preds if p.true_label == c)
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if support else None)
        out[c] = {
            "precision": _r(prec),
            "recall": _r(rec),
            "f1": _r(f1),
            "support": support,
        }
    return out


def macro_f1(prf: dict[str, dict[str, Any]]) -> float:
    """Mean F1 over classes with nonzero support and a defined F1."""
    f1s = [v["f1"] for v in prf.values() if v["support"] and v["f1"] is not None]
    return round(sum(f1s) / len(f1s), 4) if f1s else 0.0


# -- business metrics ------------------------------------------------------
def business_metrics(preds: list[AbsencePrediction], manifest: DatasetManifest) -> dict[str, Any]:
    """The decision-cost metrics the USP lives or dies on (spec §33.5)."""
    arche = {(c.material_id, c.property_id): c.archetype for c in manifest.cells}
    pm = [p for p in preds if p.true_label == POSSIBLE_MISS]
    gg = [p for p in preds if p.true_label == GENUINE_GAP]
    fm = [p for p in gg if arche.get((p.material_id, p.property_id)) == "FALSE_MISS"]
    ab = [p for p in gg if arche.get((p.material_id, p.property_id)) == "ABSENT"]
    n_abstain = sum(1 for p in preds if p.verdict == "abstain")
    decided = [p for p in preds if p.verdict != "abstain"]
    return {
        "false_gap_rate": _rate(sum(1 for p in pm if p.verdict == GENUINE_GAP), len(pm)),
        "miss_detection_recall": _rate(sum(1 for p in pm if p.verdict == POSSIBLE_MISS), len(pm)),
        "false_possible_miss_rate": _rate(
            sum(1 for p in gg if p.verdict == POSSIBLE_MISS), len(gg)
        ),
        "no_data_recall": _rate(sum(1 for p in gg if p.verdict == GENUINE_GAP), len(gg)),
        "false_miss_called_possible_miss": _rate(
            sum(1 for p in fm if p.verdict == POSSIBLE_MISS), len(fm)
        ),
        "clean_absent_called_genuine_gap": _rate(
            sum(1 for p in ab if p.verdict == GENUINE_GAP), len(ab)
        ),
        "abstention_rate": _rate(n_abstain, len(preds)),
        "selective_accuracy": _rate(sum(1 for p in decided if p.correct), len(decided)),
        "accuracy": _rate(sum(1 for p in preds if p.correct), len(preds)),
        "support": {
            "possible_miss": len(pm),
            "genuine_gap": len(gg),
            "false_miss": len(fm),
            "clean_absent": len(ab),
        },
    }


def score_method(preds: list[AbsencePrediction], manifest: DatasetManifest) -> dict[str, Any]:
    """Full per-method score block: matrix + per-class + macro-F1 + business."""
    prf = per_class_prf(preds)
    return {
        "confusion_matrix": confusion_matrix(preds),
        "per_class": prf,
        "macro_f1": macro_f1(prf),
        "business": business_metrics(preds, manifest),
        "predictions": [p.to_dict() for p in preds],
    }


# -- value-signal detector diagnostics -------------------------------------
def _property_aliases(store: KuzuGraphStore, manifest: DatasetManifest) -> dict[str, list[str]]:
    """property_id → surface forms, read from each Property node's ``aliases_text``."""
    out: dict[str, list[str]] = {}
    for pid in manifest.properties:
        nd = store.get_node(pid)
        text = (nd or {}).get("aliases_text", "") or ""
        out[pid] = [a for a in text.split("|") if a]
    return out


def _mention_texts(store: KuzuGraphStore, manifest: DatasetManifest) -> dict[str, str]:
    """cell.key() → the prose text of the cell's document (chunk cells only)."""
    cache: dict[str, str] = {}
    out: dict[str, str] = {}
    for cell in manifest.cells:
        if cell.source_modality != "chunk" or not cell.doc_id:
            continue
        if cell.doc_id not in cache:
            rows = store.rows(
                "MATCH (d:Node {id:$did})-[r:Rel]->(c:Node) "
                "WHERE r.type='HAS_CHUNK' AND c.label='Chunk' RETURN c.text",
                {"did": cell.doc_id},
            )
            cache[cell.doc_id] = " ".join(r[0] for r in rows if r[0])
        out[cell.key()] = cache[cell.doc_id]
    return out


def _value_signal(
    manifest: DatasetManifest,
    mention_texts: dict[str, str],
    aliases: dict[str, list[str]],
) -> dict[str, Any]:
    """P/R/F1 of the offline D1 regex vs the oracle ``measurable_in_source``, over
    the discriminator cells only (mentioned TRUE_MISS / FALSE_MISS)."""
    tp = fp = tn = fn = 0
    n = 0
    for cell in manifest.cells:
        if not cell.mentioned_in_source or cell.archetype not in ("TRUE_MISS", "FALSE_MISS"):
            continue
        truth = bool(cell.measurable_in_source)
        text = mention_texts.get(cell.key(), "")
        pred = value_present_in_text(text, aliases.get(cell.property_id, []))
        n += 1
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if (tp + fn) else None)
    return {
        "precision": _r(prec),
        "recall": _r(rec),
        "f1": _r(f1),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "n": n,
        "note": "offline D1 regex vs ground-truth measurable_in_source, on the "
        "TRUE_MISS/FALSE_MISS discriminator cells",
    }


# -- probability / threshold / bootstrap -----------------------------------
def _probability(sigs: dict[str, dict[str, Any]], manifest: DatasetManifest) -> dict[str, Any]:
    """Calibration of ``p_extractor_missed`` vs the miss event, over the probabilistic
    zone (cells with no active observation and no retraction)."""
    p: list[float] = []
    y: list[int] = []
    for cell in manifest.cells:
        s = sigs[cell.key()]
        if s["active"] == 0 and s["retracted"] == 0:
            p.append(s["p_missed"])
            y.append(1 if cell.true_label == POSSIBLE_MISS else 0)
    return calibration.probability_report(p, y)


def _threshold_study(sigs: dict[str, dict[str, Any]], manifest: DatasetManifest) -> dict[str, Any]:
    cells = [
        {
            "key": cell.key(),
            "true_label": cell.true_label,
            "active": sigs[cell.key()]["active"],
            "retracted": sigs[cell.key()]["retracted"],
            "mentioned": sigs[cell.key()]["mentioned"],
            "p_missed": sigs[cell.key()]["p_missed"],
        }
        for cell in manifest.cells
    ]
    return calibration.select_thresholds(cells)


def _bootstrap_accuracy(methods_out: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    out: dict[str, Any] = {}
    for method, blk in methods_out.items():
        correct = [1.0 if p["correct"] else 0.0 for p in blk["predictions"]]
        out[method] = calibration.bootstrap_ci(correct, np.mean)
    return out


# -- orchestration ---------------------------------------------------------
def evaluate_absence(
    store: KuzuGraphStore,
    manifest: DatasetManifest,
    *,
    recall_prior: float = 0.3,
    prose_extraction_enabled: bool = False,
    calibrate: bool = True,
    bootstrap: bool = True,
) -> dict[str, Any]:
    """Score the whole method ladder over a seeded store + its manifest, and attach
    the probability / threshold / Track-A / guardrail / value-signal analyses."""
    # Compute per-cell signals + the real value-gate verdict ONCE, then reuse.
    sigs: dict[str, dict[str, Any]] = {}
    gate_verdicts: dict[str, str] = {}
    for cell in manifest.cells:
        sigs[cell.key()] = _signals(
            store, cell.material_id, cell.property_id, recall_prior=recall_prior
        )
        gate_verdicts[cell.key()] = classify_cell(
            store, cell.material_id, cell.property_id, recall_prior=recall_prior, value_gate=True
        ).verdict

    mention_texts = _mention_texts(store, manifest)
    aliases = _property_aliases(store, manifest)

    def _score(method: str, *, calibrated: bool = False) -> dict[str, Any]:
        preds = _predictions(
            manifest,
            method,
            sigs=sigs,
            gate_verdicts=gate_verdicts,
            calibrated=calibrated,
            mention_texts=mention_texts,
            aliases=aliases,
        )
        return score_method(preds, manifest)

    methods_out: dict[str, Any] = {}
    for method in (*BASELINES, "absence_confidence", *VALUE_METHODS):
        methods_out[method] = _score(method)

    # Probability + cost-threshold study on the current layer.
    methods_out["absence_confidence"]["probability"] = _probability(sigs, manifest)
    methods_out["absence_confidence"]["threshold_study"] = _threshold_study(sigs, manifest)

    track_a = matching.evaluate_extraction_semantic(
        store, manifest.extraction_gold, profile=manifest.profile
    )
    guard = guardrails.check_recall_priors(
        track_a, prose_extraction_enabled=prose_extraction_enabled
    )

    if calibrate:
        # SOTA note: classify_cell uses a fixed MENTION_EXISTS_PRIOR for mentioned
        # cells, so gold-recall calibration leaves the mention-based verdicts here
        # unchanged — it changes probability quality, NOT the mention-vs-value
        # confusion (which is structural). Recorded so the report can say so.
        cal = methods_out["absence_confidence_calibrated"] = _score(
            "absence_confidence_calibrated", calibrated=True
        )
        cal["probability"] = _probability(sigs, manifest)
        cal["calibrated"] = True

    payload: dict[str, Any] = {
        "dataset": {
            "name": manifest.name,
            "seed": manifest.seed,
            "profile": manifest.profile,
            "n_cells": len(manifest.cells),
            "label_histogram": manifest.label_histogram(),
            "notes": list(manifest.notes),
        },
        "recall_prior": recall_prior,
        "methods": methods_out,
        "extraction_track_a": track_a,
        "guardrails": guard,
        "value_signal": _value_signal(manifest, mention_texts, aliases),
    }
    if bootstrap:
        payload["bootstrap"] = _bootstrap_accuracy(methods_out)
    return payload


def run(
    *,
    n_materials: int = 12,
    seed: int = 20260701,
    profile: str = "offline",
    recall_prior: float = 0.3,
    calibrate: bool = True,
    bootstrap: bool = True,
) -> dict[str, Any]:
    """Generate the synthetic corpus into an isolated store and score Track-C.

    Fully offline and deterministic; the store is a throwaway temp dir, never a
    production graph. ``profile`` labels the recall regime for the guardrail.
    """
    import tempfile
    from pathlib import Path

    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    try:
        manifest = build_synthetic(store, n_materials=n_materials, seed=seed, profile=profile)
        return evaluate_absence(
            store,
            manifest,
            recall_prior=recall_prior,
            prose_extraction_enabled=profile != "offline",
            calibrate=calibrate,
            bootstrap=bootstrap,
        )
    finally:
        store.close()
