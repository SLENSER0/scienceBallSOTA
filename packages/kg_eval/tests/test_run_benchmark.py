"""[DE] Benchmark orchestrator, report, and regression guard (§33.10 A1/A5, D12/D13)."""

from __future__ import annotations

import functools
import json
import tempfile
from pathlib import Path

from kg_eval import absence_reports
from kg_eval.run_benchmark import _cli, compare, run, run_regression_check


@functools.lru_cache(maxsize=1)
def _report() -> dict:
    return run(profile="offline")


def test_run_builds_report_with_provenance_and_written_files() -> None:
    out = tempfile.mkdtemp()
    rep = run(profile="offline", out_dir=out)
    assert rep["schema"] == "kg_eval.benchmark/absence/v1"
    assert rep["track"] == "absence"
    assert rep["provenance"]["backend"] == "embedded"
    assert Path(rep["_written"]["json"]).exists()
    md = Path(rep["_written"]["markdown"]).read_text(encoding="utf-8")
    # round-trip: the written json parses and carries the methods
    parsed = json.loads(Path(rep["_written"]["json"]).read_text(encoding="utf-8"))
    assert "absence_confidence_value_gate" in parsed["methods"]
    assert "# Confidence-of-absence benchmark" in md


def test_markdown_sections_present() -> None:
    md = absence_reports.to_markdown(_report())
    for heading in (
        "## Run provenance",
        "## Leaderboard",
        "## Track-A extraction reality",
        "## Guardrails",
        "## Value-in-mention signal",
        "## Honest findings",
    ):
        assert heading in md
    # profile-aware: the mention-vs-value confusion is named because fpm > 0.
    assert "mention-vs-value confusion" in md


def test_regression_check_reproduces_the_collapse() -> None:
    res = run_regression_check()
    assert res["regression_detected"] is True
    assert res["accuracy_drop"] > 0
    assert res["abstention_jump"] >= 0.10
    # prose OFF decides (0 abstain); prose ON collapses into the abstain band.
    assert res["prose_off"]["abstention_rate"] == 0.0
    assert res["prose_on"]["abstention_rate"] > 0.4
    assert res["prose_on"]["accuracy"] < res["prose_off"]["accuracy"]


def test_cli_regression_exits_1() -> None:
    assert _cli(["--regression"]) == 1  # regression detected → CI gate fires
    assert _cli(["--profile", "offline"]) == 0  # normal run → 0


def test_compare_produces_paired_deltas() -> None:
    d = tempfile.mkdtemp()
    run(profile="offline", out_dir=d)
    jp = str(Path(d) / "report.json")
    cmp = compare(jp, jp)  # compare a report to itself → zero deltas
    assert cmp["schema"] == "kg_eval.benchmark/compare/v1"
    ac = cmp["methods"]["absence_confidence"]
    assert ac["accuracy"]["delta"] == 0.0
    assert ac["false_possible_miss_rate"]["delta"] == 0.0
