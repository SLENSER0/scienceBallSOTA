"""Tests for expert-feedback regression cases (§23.22)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_eval.feedback_regression_case import (
    RegressionCase,
    dedup,
    from_feedback,
)


def _wrong_number_fb() -> dict[str, object]:
    return {
        "id": "fb-1",
        "type": "wrong_number",
        "question": "What is the binding affinity?",
        "wrong_value": "0.5",
        "correct_value": "0.83",
    }


def test_wrong_number_maps_forbidden_and_expected() -> None:
    """wrong_number: forbidden has the wrong value, expected has the correct one."""
    case = from_feedback(_wrong_number_fb())
    assert "0.5" in case.forbidden_substrings
    assert "0.83" in case.expected_substrings
    assert case.category == "numeric_accuracy"


def test_missing_evidence_category_and_empty_forbidden() -> None:
    """missing_evidence: category is evidence_required and forbidden is empty."""
    case = from_feedback(
        {
            "id": "fb-2",
            "type": "missing_evidence",
            "question": "Which paper supports this?",
        }
    )
    assert case.category == "evidence_required"
    assert case.forbidden_substrings == ()


def test_same_question_and_type_give_identical_case_id() -> None:
    """Identical question + type must yield the same deterministic case_id."""
    a = from_feedback(_wrong_number_fb())
    b = from_feedback(_wrong_number_fb())
    assert a.case_id == b.case_id


def test_dedup_of_three_with_one_dup_yields_two() -> None:
    """Three cases with one duplicate collapse to two, keeping the first."""
    a = from_feedback(_wrong_number_fb())
    b = from_feedback(_wrong_number_fb())  # duplicate of a
    other = from_feedback(
        {
            "id": "fb-3",
            "type": "missing_evidence",
            "question": "Which paper supports this?",
        }
    )
    result = dedup([a, b, other])
    assert len(result) == 2
    ids = [c.case_id for c in result]
    assert ids == sorted(ids)


def test_case_id_prefix_and_length() -> None:
    """case_id starts with 'reg-' and is exactly 16 characters long."""
    case = from_feedback(_wrong_number_fb())
    assert case.case_id.startswith("reg-")
    assert len(case.case_id) == 16


def test_as_dict_expected_substrings_is_list() -> None:
    """as_dict() serialises expected_substrings as a list, not a tuple."""
    case = from_feedback(_wrong_number_fb())
    d = case.as_dict()
    assert isinstance(d["expected_substrings"], list)
    assert d["expected_substrings"] == ["0.83"]


def test_regression_case_is_frozen() -> None:
    """RegressionCase instances are immutable (frozen dataclass)."""
    case = from_feedback(_wrong_number_fb())
    assert isinstance(case, RegressionCase)
    with pytest.raises(FrozenInstanceError):
        case.category = "changed"  # type: ignore[misc]
