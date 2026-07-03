"""Tests for the recall-by-modality report (§25.9).

Every expected number is hand-derived from this fixed prior set:

    prose/llm         recall 0.9  calibrated
    prose/rule        recall 0.7  calibrated
    table_row/llm     recall 0.5  heuristic
    catalog_row/rule  recall 0.3  heuristic
"""

from __future__ import annotations

import pytest

from kg_retrievers.recall_report import (
    DEFAULT_WEAKEST_N,
    RecallReport,
    build_recall_report,
)


def _priors() -> list[dict]:
    return [
        {"target_type": "prose", "extractor": "llm", "recall": 0.9, "calibrated": True},
        {"target_type": "prose", "extractor": "rule", "recall": 0.7, "calibrated": True},
        {"target_type": "table_row", "extractor": "llm", "recall": 0.5, "calibrated": False},
        {"target_type": "catalog_row", "extractor": "rule", "recall": 0.3, "calibrated": False},
    ]


def test_by_modality_averages() -> None:
    # prose = (0.9 + 0.7) / 2 = 0.8; the single-cell modalities pass through.
    report = build_recall_report(_priors())

    assert report.by_modality == {
        "catalog_row": pytest.approx(0.3),
        "prose": pytest.approx(0.8),
        "table_row": pytest.approx(0.5),
    }


def test_by_extractor_averages() -> None:
    # llm = (0.9 + 0.5) / 2 = 0.7; rule = (0.7 + 0.3) / 2 = 0.5.
    report = build_recall_report(_priors())

    assert report.by_extractor == {
        "llm": pytest.approx(0.7),
        "rule": pytest.approx(0.5),
    }


def test_weakest_sorted_ascending() -> None:
    # Default flags the DEFAULT_WEAKEST_N lowest-recall cells, weakest first.
    report = build_recall_report(_priors())

    assert len(report.weakest) == DEFAULT_WEAKEST_N == 3
    assert [c.recall for c in report.weakest] == [
        pytest.approx(0.3),
        pytest.approx(0.5),
        pytest.approx(0.7),
    ]
    assert report.weakest[0].modality == "catalog_row"
    assert report.weakest[0].extractor == "rule"


def test_weakest_n_can_return_all_cells() -> None:
    # A larger cutoff surfaces every cell, still fully sorted by ascending recall.
    report = build_recall_report(_priors(), weakest_n=10)

    assert [c.recall for c in report.weakest] == [
        pytest.approx(0.3),
        pytest.approx(0.5),
        pytest.approx(0.7),
        pytest.approx(0.9),
    ]


def test_weakest_ties_break_by_modality_then_extractor() -> None:
    # Equal recall → deterministic order: modality first ("a" < "b"), then extractor.
    priors = [
        {"target_type": "b", "extractor": "z", "recall": 0.5, "calibrated": True},
        {"target_type": "a", "extractor": "y", "recall": 0.5, "calibrated": True},
        {"target_type": "a", "extractor": "x", "recall": 0.5, "calibrated": True},
    ]
    report = build_recall_report(priors, weakest_n=3)

    assert [(c.modality, c.extractor) for c in report.weakest] == [
        ("a", "x"),
        ("a", "y"),
        ("b", "z"),
    ]


def test_calibrated_share_is_a_fraction() -> None:
    # 2 of 4 priors are calibrated → share = 0.5 (the rest are heuristic).
    report = build_recall_report(_priors())

    assert report.calibrated_share == pytest.approx(0.5)


def test_empty_priors_yield_zeros() -> None:
    report = build_recall_report([])

    assert isinstance(report, RecallReport)
    assert report.by_modality == {}
    assert report.by_extractor == {}
    assert report.weakest == ()
    assert report.calibrated_share == 0.0


def test_single_prior() -> None:
    priors = [{"target_type": "prose", "extractor": "llm", "recall": 0.42, "calibrated": True}]
    report = build_recall_report(priors)

    assert report.by_modality == {"prose": pytest.approx(0.42)}
    assert report.by_extractor == {"llm": pytest.approx(0.42)}
    assert len(report.weakest) == 1
    assert report.weakest[0].recall == pytest.approx(0.42)
    assert report.calibrated_share == pytest.approx(1.0)


def test_as_dict_shape_and_values() -> None:
    report = build_recall_report(_priors())
    dumped = report.as_dict()

    assert set(dumped) == {"by_modality", "by_extractor", "weakest", "calibrated_share"}
    assert dumped["by_modality"]["prose"] == pytest.approx(0.8)
    assert dumped["by_extractor"]["llm"] == pytest.approx(0.7)
    assert dumped["calibrated_share"] == pytest.approx(0.5)
    assert isinstance(dumped["weakest"], list)
    assert dumped["weakest"][0] == {
        "modality": "catalog_row",
        "extractor": "rule",
        "recall": pytest.approx(0.3),
        "calibrated": False,
    }
