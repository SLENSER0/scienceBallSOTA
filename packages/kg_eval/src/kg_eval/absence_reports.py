"""[DE] Confidence-of-absence report builder (spec §33.10 A1, port of science_ball reports).

Pure formatting / diffing of a benchmark payload into ``report.json`` + ``report.md``.
Never touches the graph. The findings are **profile-aware**: the mention-vs-value
confusion is only named as THE failure mode when ``false_possible_miss_rate > 0``;
when it is 0 but abstention is high, the report says the confusion is *deferred, not
solved*.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kg_eval.schemas import REALITIES, VERDICTS
from kg_retrievers.absence_signals import GENUINE_GAP_AT, POSSIBLE_MISS_AT

_METHOD_ORDER = [
    "naive_graph",
    "mentions_heuristic",
    "static_modality",
    "absence_confidence",
    "absence_confidence_calibrated",
    "absence_confidence_value_oracle",
    "absence_confidence_value_regex",
    "absence_confidence_value_gate",
]


def build(payload: dict[str, Any], *, stamped_at: str | None = None) -> dict[str, Any]:
    """Wrap a raw payload with the reproducibility envelope."""
    return {
        "schema": "kg_eval.benchmark/absence/v1",
        "generated_at": stamped_at or "unstamped",
        "track": "absence",
        **payload,
    }


def write(report: dict[str, Any], out_dir: str) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "report.json"
    mp = out / "report.md"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.write_text(to_markdown(report), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)


def _ordered(methods: dict[str, Any]) -> list[str]:
    known = [m for m in _METHOD_ORDER if m in methods]
    return known + [m for m in methods if m not in known]


def _confusion_md(cm: dict[str, dict[str, int]]) -> str:
    lines = ["**Confusion matrix**", "", "| true ↓ / pred → | " + " | ".join(VERDICTS) + " |"]
    lines.append("|" + "---|" * (len(VERDICTS) + 1))
    for r in REALITIES:
        cells = " | ".join(str(cm.get(r, {}).get(v, 0)) for v in VERDICTS)
        lines.append(f"| **{r}** | {cells} |")
    return "\n".join(lines)


def _extraction_md(tra: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Track-A extraction reality (what the pipeline actually commits)",
        "",
        "| modality | expected | semantic recall | evidence recall | value precision |",
        "| --- | --- | --- | --- | --- |",
    ]
    for mod, a in sorted((tra.get("by_modality") or {}).items()):
        lines.append(
            f"| {mod} | {a.get('expected', '—')} | {_fmt(a.get('semantic_recall'))} | "
            f"{_fmt(a.get('evidence_recall'))} | {_fmt(a.get('value_precision'))} |"
        )
    lines.append(
        f"- deterministic (table+catalog) semantic recall: "
        f"**{_fmt(tra.get('deterministic_semantic_recall'))}**"
    )
    if tra.get("prose_note"):
        lines.append(f"> {tra['prose_note']}")
    return lines


def _guardrails_md(gr: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Guardrails — recall prior vs measured recall",
        "",
        "| modality | prior | measured recall | divergence | over tolerance |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in gr.get("checks", []):
        flag = "⚠️ YES" if c.get("over_tolerance") else "no"
        lines.append(
            f"| {c.get('modality')} | {_fmt(c.get('prior'))} | {_fmt(c.get('measured_recall'))} "
            f"| {_fmt(c.get('divergence'))} | {flag} |"
        )
    if gr.get("findings"):
        lines.extend(f"- ⚠️ {f}" for f in gr["findings"])
    else:
        lines.append(f"- All priors within tolerance ({_fmt(gr.get('tolerance'))}).")
    return lines


def _value_signal_md(vs: dict[str, Any]) -> list[str]:
    c = vs.get("confusion", {})
    lines = [
        "",
        "## Value-in-mention signal (A7 — the offline fix for mention-vs-value)",
        "",
        f"- detector precision / recall / F1 vs ground-truth measurable value: "
        f"**{_fmt(vs.get('precision'))} / {_fmt(vs.get('recall'))} / {_fmt(vs.get('f1'))}** "
        f"(n={vs.get('n')}; tp={c.get('tp')} fp={c.get('fp')} tn={c.get('tn')} fn={c.get('fn')})",
    ]
    if vs.get("note"):
        lines.append(f"> {vs['note']}")
    return lines


def _findings(
    methods: dict[str, Any], ds: dict[str, Any], prov: dict[str, Any] | None
) -> list[str]:
    prov = prov or {}
    cur = methods.get("absence_confidence", {}).get("business", {})
    naive = methods.get("naive_graph", {}).get("business", {})
    profile = prov.get("profile")
    prose_on = prov.get("prose_extraction_enabled")
    abst = cur.get("abstention_rate")
    mdr = cur.get("miss_detection_recall")
    fpm = cur.get("false_possible_miss_rate")
    out: list[str] = []

    if profile is not None:
        out.append(
            f"- Profile `{profile}` (prose_extraction_enabled=`{prose_on}`): ground-truth "
            f"labels are pinned to this regime — read every metric against THIS profile only."
        )
    if abst is not None and abst >= 0.2:
        band = f"[{GENUINE_GAP_AT}, {POSSIBLE_MISS_AT})"
        out.append(
            f"- **Abstain-band collapse**: the current system abstains on **{_fmt(abst)}** of "
            f"cells — `p_extractor_missed` for mentioned-but-unobserved cells sits inside the "
            f"{band} abstain band, so it DEFERS instead of deciding (miss-detection recall is "
            f"**{_fmt(mdr)}**). Signature of a mis-grounded recall prior, not a data problem."
        )
    if fpm is not None and fpm > 0:
        out.append(
            f"- The current system catches **{_fmt(mdr)}** of real extractor misses but wrongly "
            f"flags **{_fmt(fpm)}** of genuine gaps as `possible_miss` — it cannot distinguish "
            f"*a property being named* from *a measurable value being stated*. This mention-vs-"
            f"value confusion is the top structural target (a measurable-value-in-mention signal)."
        )
    elif fpm == 0 and abst and abst >= 0.2:
        out.append(
            "- `false_possible_miss_rate` is 0 here **only because the layer abstains**, not "
            "because it tells named-vs-measured apart — the confusion is deferred, not solved."
        )

    heur = methods.get("absence_confidence", {}).get("macro_f1")
    cal = methods.get("absence_confidence_calibrated", {}).get("macro_f1")
    if heur is not None and cal is not None and abs(heur - cal) >= 0.02:
        out.append(
            f"- Gold-calibrated priors move macro-F1 **{_fmt(heur)} → {_fmt(cal)}** — "
            f"recalibrating the recall prior materially changes the verdict here."
        )
    elif "absence_confidence_calibrated" in methods:
        out.append(
            "- Calibration replaces heuristic recall priors with gold-measured ones; here it "
            "leaves the mention-based verdicts unchanged (SOTA uses a fixed mention prior), so it "
            "does NOT touch the mention-vs-value confusion — that is structural, not calibration."
        )

    oracle = methods.get("absence_confidence_value_oracle", {})
    o_f1 = oracle.get("macro_f1")
    base_f1 = methods.get("absence_confidence", {}).get("macro_f1")
    o_fpm = oracle.get("business", {}).get("false_possible_miss_rate")
    if o_f1 is not None and base_f1 is not None and o_f1 - base_f1 >= 0.02:
        out.append(
            f"- **Achievable fix (A7)**: a measurable-value-in-mention signal moves macro-F1 "
            f"**{_fmt(base_f1)} → {_fmt(o_f1)}** and false-possible-miss-rate → **{_fmt(o_fpm)}** "
            f"(oracle ceiling)."
        )
    gate = methods.get("absence_confidence_value_gate", {})
    g_f1 = gate.get("macro_f1")
    if g_f1 is not None and base_f1 is not None and g_f1 - base_f1 >= 0.02:
        out.append(
            f"- The **real production value gate** (opt-in `absence_value_gate`) reaches macro-F1 "
            f"**{_fmt(g_f1)}** on this corpus — it reads `value_present` off the graph, so it "
            f"matches the oracle without an LLM. The offline regex approximates it from text."
        )
    if naive and cur:
        out.append(
            f"- Ablation: the naive-graph baseline has false-gap rate "
            f"{_fmt(naive.get('false_gap_rate'))} and miss-detection recall "
            f"{_fmt(naive.get('miss_detection_recall'))} (it never flags a miss); the absence "
            f"layer trades some `possible_miss` precision for real miss detection."
        )
    out.append(
        "- All numbers are on a small synthetic set; treat CIs (not point estimates) as the "
        "claim, and see §33 for the path to an expert gold benchmark."
    )
    return out


def to_markdown(report: dict[str, Any]) -> str:
    prov = report.get("provenance", {})
    ds = report.get("dataset", {})
    methods = report.get("methods", {})
    boot = report.get("bootstrap", {})
    md: list[str] = [
        "# Confidence-of-absence benchmark — report",
        "",
        f"*Generated {report.get('generated_at', '?')}, track = {report.get('track', '?')}*",
        "",
        "## Run provenance",
    ]
    for k in (
        "git_commit", "package_version", "python", "backend",
        "profile", "prose_extraction_enabled", "n_materials", "seed", "dataset",
    ):  # fmt: skip
        if k in prov:
            md.append(f"- **{k}**: `{prov[k]}`")
    md.append(
        f"**Dataset**: {ds.get('name', '?')} · {ds.get('n_cells', '?')} cells · "
        f"labels {ds.get('label_histogram', {})}"
    )
    md += ["", "## Leaderboard (macro-F1, accuracy, and the two business metrics)", ""]
    md.append(
        "| method | macro-F1 | accuracy | miss-detection recall ↑ | false-gap rate ↓ | "
        "false-possible-miss ↓ | abstain | acc 95% CI |"
    )
    md.append("|" + "---|" * 8)
    for m in _ordered(methods):
        res = methods[m]
        b = res.get("business", {})
        ci = boot.get(m, {})
        ci_s = f"[{_fmt(ci.get('lo'))}, {_fmt(ci.get('hi'))}]" if ci else "—"
        name = f"**{m}**" if m.startswith("absence_confidence") else m
        md.append(
            f"| {name} | {_fmt(res.get('macro_f1'))} | {_fmt(b.get('accuracy'))} | "
            f"{_fmt(b.get('miss_detection_recall'))} | {_fmt(b.get('false_gap_rate'))} | "
            f"{_fmt(b.get('false_possible_miss_rate'))} | "
            f"{_fmt(b.get('abstention_rate'))} | {ci_s} |"
        )

    for m in ("absence_confidence", "absence_confidence_calibrated"):
        if m not in methods:
            continue
        md += ["", f"## `{m}` — per-class precision / recall / F1", ""]
        md += ["| class | precision | recall | F1 | support |", "| --- | --- | --- | --- | --- |"]
        pc = methods[m].get("per_class", {})
        for c in REALITIES:
            row = pc.get(c, {})
            md.append(
                f"| {c} | {_fmt(row.get('precision'))} | {_fmt(row.get('recall'))} | "
                f"{_fmt(row.get('f1'))} | {row.get('support', '—')} |"
            )
        md += ["", _confusion_md(methods[m]["confusion_matrix"])]
        prob = methods[m].get("probability")
        if prob:
            md.append(
                f"\n**Probability quality** (`p_extractor_missed` vs true miss, n={prob['n']}, "
                f"base rate {_fmt(prob['base_rate'])}): Brier {_fmt(prob['brier'])} · "
                f"ECE {_fmt(prob['ece'])} · AUROC {_fmt(prob['auroc'])} · "
                f"AUPRC {_fmt(prob['auprc'])} · log-loss {_fmt(prob['log_loss'])}."
            )
            md.append(f"> scope: {prob.get('scope')}")

    ts = methods.get("absence_confidence", {}).get("threshold_study")
    if ts:
        sel = ts.get("selected", {})
        md += ["", "## Cost-based threshold study (held-out split; NOT written back)"]
        md.append(
            f"- selected on calibration split: `possible_miss_at={sel.get('possible_miss_at')}`, "
            f"`genuine_gap_at={sel.get('genuine_gap_at')}` (calib mean cost "
            f"{_fmt(sel.get('calib_cost'))})"
        )
        md.append(
            f"- **test mean cost**: selected {_fmt(ts.get('test_cost_selected'))} vs production "
            f"0.60/0.25 {_fmt(ts.get('test_cost_production_0.60_0.25'))}"
        )
        md.append(
            f"- n_calib={ts.get('n_calib')}, n_test={ts.get('n_test')} — {ts.get('note', '')}"
        )

    if report.get("extraction_track_a"):
        md += _extraction_md(report["extraction_track_a"])
    if report.get("guardrails"):
        md += _guardrails_md(report["guardrails"])
    if report.get("value_signal"):
        md += _value_signal_md(report["value_signal"])
    md += ["", "## Honest findings"]
    md += _findings(methods, ds, prov)
    return "\n".join(md)


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Paired per-method deltas between two reports."""
    om, nm = old.get("methods", {}), new.get("methods", {})
    metrics = (
        "accuracy", "miss_detection_recall", "false_gap_rate",
        "false_possible_miss_rate", "no_data_recall", "abstention_rate",
    )  # fmt: skip
    methods: dict[str, Any] = {}
    for m in sorted(set(om) | set(nm)):
        ob = om.get(m, {}).get("business", {})
        nb = nm.get(m, {}).get("business", {})
        row: dict[str, Any] = {}
        for k in metrics:
            o, n = ob.get(k), nb.get(k)
            delta = (
                round(n - o, 4)
                if isinstance(o, (int, float)) and isinstance(n, (int, float))
                else None
            )
            row[k] = {"old": o, "new": n, "delta": delta}
        row["macro_f1"] = {
            "old": om.get(m, {}).get("macro_f1"),
            "new": nm.get(m, {}).get("macro_f1"),
        }
        methods[m] = row
    return {
        "schema": "kg_eval.benchmark/compare/v1",
        "old_provenance": old.get("provenance"),
        "new_provenance": new.get("provenance"),
        "methods": methods,
    }
