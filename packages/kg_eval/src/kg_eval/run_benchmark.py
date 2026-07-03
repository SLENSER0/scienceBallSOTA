"""[DE] Confidence-of-absence benchmark runner + regression guard + CLI (spec §33.10 A5).

Orchestration entry point. ``run`` scores Track-C over an isolated synthetic corpus
and emits ``report.json`` / ``report.md``. ``run_regression_check`` reproduces the
§33.9 prose-prior abstain-collapse **deterministically offline** — the CI gate that
protects the absence verdict from a mis-grounded recall prior. Nothing touches the
production graph.

Usage:

    python -m kg_eval.run_benchmark --profile offline --out benchmarks/synthetic/latest
    python -m kg_eval.run_benchmark --regression   # exit 1 if a regression is detected
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from kg_eval import absence_eval, absence_reports
from kg_eval.datasets.loader import load_synthetic
from kg_eval.recall_model import base_recall
from kg_retrievers.absence_signals import (
    POSSIBLE_MISS,
    _verdict_from_p_missed,
    classify_cell,
)


def run(
    track: str = "absence",
    *,
    profile: str = "offline",
    n_materials: int = 12,
    seed: int = 20260701,
    calibrate: bool = True,
    bootstrap: bool = True,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Score Track-C over an isolated corpus and build the report (optionally write it)."""
    if track != "absence":
        raise NotImplementedError(
            f"Track {track!r} not in the vertical slice. Implemented: 'absence'. "
            f"Track 'extraction' (see kg_eval.matching) and 'query' are designed in §33."
        )
    with load_synthetic(n_materials=n_materials, seed=seed, profile=profile) as ctx:
        payload = absence_eval.evaluate_absence(
            ctx.store,
            ctx.manifest,
            prose_extraction_enabled=ctx.prose_extraction_enabled,
            calibrate=calibrate,
            bootstrap=bootstrap,
        )
        payload["provenance"] = ctx.provenance
    report = absence_reports.build(payload)
    if out_dir is not None:
        report["_written"] = absence_reports.write(report, out_dir)
    return report


def run_regression_check(
    *, n_materials: int = 12, seed: int = 20260701, abstain_jump: float = 0.10
) -> dict[str, Any]:
    """Reproduce the prose-prior abstain-collapse deterministically offline (A5).

    Scores the SAME offline corpus twice, changing ONLY the prose recall prior
    (chunk 0.15 → 0.55). SOTA's production ``classify_cell`` is immune (it uses a
    fixed high mention prior), so this **simulates** the science_ball prose-prior
    rule — the exact regression this gate would catch if the prose prior were ever
    wired into the verdict: with prior 0.55, ``p_missed = 0.45`` lands in the
    ``[GENUINE_GAP_AT, POSSIBLE_MISS_AT)`` abstain band and every prose-mentioned
    cell defers.
    """

    def _score(store: Any, manifest: Any, *, prose_on: bool) -> dict[str, Any]:
        p_prose_missed = round(1.0 - base_recall("chunk", prose_on), 3)  # 0.85 off / 0.45 on
        verds: Counter[str] = Counter()
        correct = 0
        for cell in manifest.cells:
            sig = classify_cell(store, cell.material_id, cell.property_id)
            if sig.verdict == POSSIBLE_MISS and sig.signals["mentioned_without_observation"]:
                verdict = _verdict_from_p_missed(p_prose_missed)  # the prose-prior rule
            else:
                verdict = sig.verdict
            verds[verdict] += 1
            correct += int(verdict == cell.true_label)
        n = len(manifest.cells) or 1
        return {
            "prose_extraction_enabled": prose_on,
            "accuracy": round(correct / n, 4),
            "abstention_rate": round(verds["abstain"] / n, 4),
            "verdicts": dict(verds),
        }

    with load_synthetic(n_materials=n_materials, seed=seed, profile="offline") as ctx:
        off = _score(ctx.store, ctx.manifest, prose_on=False)
        on = _score(ctx.store, ctx.manifest, prose_on=True)

    acc_drop = round(off["accuracy"] - on["accuracy"], 4)
    abst_jump = round(on["abstention_rate"] - off["abstention_rate"], 4)
    regression = acc_drop > 0 and abst_jump >= abstain_jump
    return {
        "schema": "kg_eval.benchmark/regression/v1",
        "prose_off": off,
        "prose_on": on,
        "accuracy_drop": acc_drop,
        "abstention_jump": abst_jump,
        "abstain_jump_threshold": abstain_jump,
        "regression_detected": regression,
        "explanation": (
            "Enabling the prose extractor raises the chunk recall prior 0.15→0.55, so "
            "prose-mentioned cells fall into the [GENUINE_GAP_AT, POSSIBLE_MISS_AT) abstain "
            "band: the live-llm collapse, reproduced offline by toggling only the prior."
            if regression
            else "No cross-profile regression detected."
        ),
    }


def load_report(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare(old_path: str, new_path: str) -> dict[str, Any]:
    return absence_reports.compare(load_report(old_path), load_report(new_path))


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="run_benchmark", description="Materials-KG confidence-of-absence benchmark runner"
    )
    ap.add_argument("--track", default="absence")
    ap.add_argument("--profile", default="offline", choices=["offline", "live-llm"])
    ap.add_argument("--n-materials", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20260701)
    ap.add_argument("--no-calibrate", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--regression",
        action="store_true",
        help="run the A5 regression check; exit 1 on regression",
    )
    a = ap.parse_args(argv)

    if a.regression:
        res = run_regression_check(n_materials=a.n_materials, seed=a.seed)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if res["regression_detected"] else 0

    rep = run(
        a.track,
        profile=a.profile,
        n_materials=a.n_materials,
        seed=a.seed,
        calibrate=not a.no_calibrate,
        out_dir=a.out,
    )
    print(absence_reports.to_markdown(rep))
    if a.out:
        print(f"\nWrote {rep['_written']['json']} and {rep['_written']['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
