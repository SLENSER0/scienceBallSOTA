"""Tests for LitQA2-style abstention QA scoring (§23.31/§23.35).

Hand-checkable cases covering perfect answering, partial abstention, total
abstention, empty input, wrong-but-answered penalties, and the structural
invariant ``accuracy <= coverage``.
"""

from __future__ import annotations

import pytest

from kg_eval.abstention_qa_score import AbstentionScore, score


def test_all_answered_all_correct() -> None:
    records = [
        {"predicted": "answer", "correct": True},
        {"predicted": "answer", "correct": True},
        {"predicted": "answer", "correct": True},
    ]
    result = score(records)
    assert result.n == 3
    assert result.n_answered == 3
    assert result.n_correct == 3
    assert result.precision == 1.0
    assert result.coverage == 1.0
    assert result.accuracy == 1.0
    assert result.litqa_score == 1.0


def test_partial_abstention_half_answered_one_correct() -> None:
    # 4 records: 2 answered (1 correct, 1 wrong), 2 unsure.
    records = [
        {"predicted": "answer", "correct": True},
        {"predicted": "answer", "correct": False},
        {"predicted": "unsure", "correct": False},
        {"predicted": "unsure", "correct": True},  # correct ignored on abstain
    ]
    result = score(records)
    assert result.n == 4
    assert result.n_answered == 2
    assert result.n_correct == 1
    assert result.precision == 0.5  # 1 / 2
    assert result.coverage == 0.5  # 2 / 4
    assert result.accuracy == 0.25  # 1 / 4
    assert result.litqa_score == 0.25  # 0.5 * 0.5


def test_all_unsure() -> None:
    records = [
        {"predicted": "unsure", "correct": False},
        {"predicted": "unsure", "correct": False},
    ]
    result = score(records)
    assert result.n_answered == 0
    assert result.coverage == 0.0
    assert result.precision == 1.0  # nothing answered -> no penalty
    assert result.accuracy == 0.0
    assert result.litqa_score == 0.0  # 1.0 * 0.0


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        score([])


def test_wrong_but_answered_lowers_precision() -> None:
    records = [
        {"predicted": "answer", "correct": True},
        {"predicted": "answer", "correct": True},
        {"predicted": "answer", "correct": False},  # wrong commit
    ]
    result = score(records)
    assert result.coverage == 1.0
    assert result.precision < 1.0
    assert result.precision == pytest.approx(2 / 3)
    assert result.litqa_score == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    "records",
    [
        [{"predicted": "answer", "correct": True}],
        [{"predicted": "unsure", "correct": False}],
        [
            {"predicted": "answer", "correct": True},
            {"predicted": "answer", "correct": False},
            {"predicted": "unsure", "correct": True},
        ],
        [
            {"predicted": "unsure", "correct": False},
            {"predicted": "answer", "correct": False},
        ],
    ],
)
def test_accuracy_never_exceeds_coverage(records: list[dict[str, object]]) -> None:
    result = score(records)
    assert result.accuracy <= result.coverage


def test_as_dict_roundtrip() -> None:
    records = [
        {"predicted": "answer", "correct": True},
        {"predicted": "unsure", "correct": False},
    ]
    result = score(records)
    assert isinstance(result, AbstentionScore)
    d = result.as_dict()
    assert d == {
        "n": 2,
        "n_answered": 1,
        "n_correct": 1,
        "precision": 1.0,
        "coverage": 0.5,
        "accuracy": 0.5,
        "litqa_score": 0.5,
    }
