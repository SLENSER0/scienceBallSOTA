"""Tests for the benchmark recall/abstention SOTA gate (§23.31/§23.35)."""

from __future__ import annotations

import dataclasses
import re

import pytest

from kg_eval import sota_recall_gate
from kg_eval.sota_recall_gate import (
    SOTA_BASELINES,
    SotaGate,
    best_baseline,
    gate,
)


def test_baselines_have_olmocr_and_omnidocbench_entries() -> None:
    # Both required benchmarks are present as {system: score} maps.
    assert "olmOCR-Bench" in SOTA_BASELINES
    assert "OmniDocBench" in SOTA_BASELINES
    assert isinstance(SOTA_BASELINES["olmOCR-Bench"], dict)
    assert isinstance(SOTA_BASELINES["OmniDocBench"], dict)


def test_numbers_match_catalog_as_reported() -> None:
    # As-reported §23.35 numbers: olmOCR-2 82.4, MinerU2.5-Pro 95.75, MinerU2.5 93.04.
    assert SOTA_BASELINES["olmOCR-Bench"]["olmOCR-2-7B-1025"] == 82.4
    assert SOTA_BASELINES["olmOCR-Bench"]["Marker"] == 76.1
    assert SOTA_BASELINES["olmOCR-Bench"]["GPT-4o"] == 68.9
    assert SOTA_BASELINES["OmniDocBench"]["MinerU2.5-Pro"] == 95.75
    assert SOTA_BASELINES["OmniDocBench"]["MinerU2.5"] == 93.04


def test_best_baseline_is_max_over_systems() -> None:
    # Best published number per benchmark is the max over its systems.
    assert best_baseline("olmOCR-Bench") == 82.4
    assert best_baseline("OmniDocBench") == 95.75


def test_beating_score_meets_sota_true() -> None:
    # 83.0 > best olmOCR-Bench (82.4) → reaches SOTA, positive gap.
    g = gate("olmOCR-Bench", 83.0)
    assert g.meets_sota is True
    assert g.best_baseline == 82.4
    assert g.gap == pytest.approx(0.6)


def test_losing_score_meets_sota_false() -> None:
    # 90.0 < best OmniDocBench (95.75) → misses SOTA, negative gap.
    g = gate("OmniDocBench", 90.0)
    assert g.meets_sota is False
    assert g.gap == pytest.approx(-5.75)


def test_tie_reaches_sota() -> None:
    # Exactly equal to best baseline → meets_sota True, gap 0.0 (no float noise).
    g = gate("olmOCR-Bench", 82.4)
    assert g.meets_sota is True
    assert g.gap == 0.0


def test_gap_is_our_score_minus_best_baseline() -> None:
    # gap = our_score - best_baseline, hand-checkable.
    g = gate("OmniDocBench", 96.0)
    assert g.our_score == 96.0
    assert g.best_baseline == 95.75
    assert g.gap == pytest.approx(0.25)
    assert g.meets_sota is True


def test_unknown_benchmark_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        gate("NoSuchBench", 99.0)
    with pytest.raises(KeyError):
        best_baseline("NoSuchBench")


def test_as_dict_shape_and_values() -> None:
    g = gate("olmOCR-Bench", 80.0)
    d = g.as_dict()
    assert set(d) == {"benchmark", "our_score", "best_baseline", "gap", "meets_sota"}
    assert d["benchmark"] == "olmOCR-Bench"
    assert d["our_score"] == 80.0
    assert d["best_baseline"] == 82.4
    assert d["gap"] == pytest.approx(-2.4)
    assert d["meets_sota"] is False


def test_frozen_dataclass() -> None:
    g = gate("olmOCR-Bench", 82.4)
    assert isinstance(g, SotaGate)
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.meets_sota = False  # type: ignore[misc]


def test_docstring_lists_olmocr_bench() -> None:
    doc = sota_recall_gate.__doc__ or ""
    assert "olmOCR-Bench" in doc


def test_docstring_cites_source_paper_or_repo() -> None:
    # Hard requirement: the module must cite an arXiv id or a github repo.
    doc = sota_recall_gate.__doc__ or ""
    has_arxiv = re.search(r"arXiv:\d{4}\.\d{4,5}", doc) is not None
    has_github = "github.com/" in doc
    assert has_arxiv and has_github
