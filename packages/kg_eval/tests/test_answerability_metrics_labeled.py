"""Hand-checkable tests for gold-labeled answerability metrics (§25.15)."""

from __future__ import annotations

from kg_eval.answerability_metrics_labeled import (
    AnswerabilityMetrics,
    answerability_metrics,
    false_gap_rate,
    no_data_genuine_gap_rate,
    no_data_precision,
    no_data_recall,
)

# Canonical §25.15 fixture (rows A..E from the spec).
ROWS = [
    {"gold": "genuine_gap", "predicted": "genuine_gap"},  # A
    {"gold": "genuine_gap", "predicted": "abstain"},  # B
    {"gold": "extraction_miss", "predicted": "possible_miss"},  # C
    {"gold": "extraction_miss", "predicted": "genuine_gap"},  # D
    {"gold": "present", "predicted": "present"},  # E
]


def test_no_data_recall_half() -> None:
    # genuine_gap golds A,B; only A predicted genuine_gap → 1/2.
    assert no_data_recall(ROWS) == 0.5


def test_no_data_precision_half() -> None:
    # predicted genuine_gap A,D; only A is gold genuine_gap → 1/2.
    assert no_data_precision(ROWS) == 0.5


def test_false_gap_rate_half() -> None:
    # extraction_miss golds C,D; only D wrongly called genuine_gap → 1/2.
    assert false_gap_rate(ROWS) == 0.5


def test_no_data_genuine_gap_rate_quarter() -> None:
    # no-data golds A,B,C,D; only A is a correct genuine_gap hit → 1/4.
    assert no_data_genuine_gap_rate(ROWS) == 0.25


def test_answerability_metrics_bundle() -> None:
    m = answerability_metrics(ROWS)
    assert isinstance(m, AnswerabilityMetrics)
    assert m.no_data_recall == 0.5
    assert m.no_data_precision == 0.5
    assert m.false_gap_rate == 0.5
    assert m.no_data_genuine_gap_rate == 0.25
    assert m.support == 5


def test_empty_input_all_zero() -> None:
    m = answerability_metrics([])
    assert m.no_data_recall == 0.0
    assert m.no_data_precision == 0.0
    assert m.false_gap_rate == 0.0
    assert m.no_data_genuine_gap_rate == 0.0
    assert m.support == 0
    assert no_data_recall([]) == 0.0
    assert no_data_precision([]) == 0.0
    assert false_gap_rate([]) == 0.0
    assert no_data_genuine_gap_rate([]) == 0.0


def test_as_dict_round_trips_five_keys() -> None:
    d = answerability_metrics(ROWS).as_dict()
    assert set(d) == {
        "no_data_recall",
        "no_data_precision",
        "false_gap_rate",
        "no_data_genuine_gap_rate",
        "support",
    }
    assert d == {
        "no_data_recall": 0.5,
        "no_data_precision": 0.5,
        "false_gap_rate": 0.5,
        "no_data_genuine_gap_rate": 0.25,
        "support": 5,
    }
