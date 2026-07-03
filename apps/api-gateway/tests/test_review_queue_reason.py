"""Тесты классификации причин и приоритизации очереди ревью (§14.14).

Tests for :mod:`api_gateway.review_queue_reason`.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from api_gateway.review_queue_reason import (
    REVIEW_REASONS,
    ReviewReason,
    classify_reason,
    priority_of,
    sort_queue,
)


def test_review_reasons_membership() -> None:
    assert isinstance(REVIEW_REASONS, frozenset)
    expected = {
        "low_confidence",
        "ambiguous_resolution",
        "contradicts_existing",
        "missing_critical_field",
        "low_quality_ocr",
        "new_schema_term",
    }
    assert expected == REVIEW_REASONS


def test_classify_low_confidence() -> None:
    assert classify_reason({"confidence": 0.3}) == "low_confidence"


def test_classify_confidence_at_threshold_not_queued() -> None:
    # 0.6 is not < 0.6, so no reason applies.
    assert classify_reason({"confidence": 0.6}) == ""


def test_classify_high_confidence_no_reason() -> None:
    assert classify_reason({"confidence": 0.9}) == ""


def test_classify_contradicts_beats_confidence() -> None:
    assert classify_reason({"contradicts": True, "confidence": 0.9}) == "contradicts_existing"


def test_classify_missing_field() -> None:
    assert classify_reason({"missing_field": "unit"}) == "missing_critical_field"


def test_classify_precedence_contradicts_over_missing() -> None:
    task = {"contradicts": True, "missing_field": "unit", "ambiguous": True}
    assert classify_reason(task) == "contradicts_existing"


def test_classify_precedence_missing_over_ambiguous() -> None:
    task = {"missing_field": "unit", "ambiguous": True, "low_quality_ocr": True}
    assert classify_reason(task) == "missing_critical_field"


def test_classify_precedence_ambiguous_over_ocr() -> None:
    task = {"ambiguous": True, "low_quality_ocr": True, "new_schema_term": True}
    assert classify_reason(task) == "ambiguous_resolution"


def test_classify_precedence_ocr_over_new_term() -> None:
    task = {"low_quality_ocr": True, "new_schema_term": True, "confidence": 0.1}
    assert classify_reason(task) == "low_quality_ocr"


def test_classify_new_term_over_confidence() -> None:
    assert classify_reason({"new_schema_term": True, "confidence": 0.1}) == "new_schema_term"


def test_classify_custom_threshold() -> None:
    assert classify_reason({"confidence": 0.7}, confidence_threshold=0.8) == "low_confidence"
    assert classify_reason({"confidence": 0.7}, confidence_threshold=0.6) == ""


def test_classify_empty_task() -> None:
    assert classify_reason({}) == ""


def test_priority_contradicts_beats_new_term() -> None:
    assert priority_of("contradicts_existing") > priority_of("new_schema_term")


def test_priority_full_ordering() -> None:
    order = [
        "contradicts_existing",
        "missing_critical_field",
        "ambiguous_resolution",
        "low_quality_ocr",
        "new_schema_term",
        "low_confidence",
    ]
    priorities = [priority_of(code) for code in order]
    assert priorities == sorted(priorities, reverse=True)
    assert len(set(priorities)) == len(priorities)


def test_priority_all_reasons_have_priority() -> None:
    for reason in REVIEW_REASONS:
        assert isinstance(priority_of(reason), int)


def test_priority_unknown_raises() -> None:
    with pytest.raises(ValueError):
        priority_of("nope")


def test_sort_queue_orders_by_priority_desc() -> None:
    tasks = [
        {"reason": "new_schema_term", "created_at": "b"},
        {"reason": "contradicts_existing", "created_at": "a"},
    ]
    ordered = sort_queue(tasks)
    assert ordered[0]["reason"] == "contradicts_existing"
    assert ordered[1]["reason"] == "new_schema_term"


def test_sort_queue_tie_break_created_at_asc() -> None:
    tasks = [
        {"reason": "low_confidence", "created_at": "2026-01-03"},
        {"reason": "low_confidence", "created_at": "2026-01-01"},
        {"reason": "low_confidence", "created_at": "2026-01-02"},
    ]
    ordered = sort_queue(tasks)
    assert [t["created_at"] for t in ordered] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]


def test_sort_queue_stable_for_equal_keys() -> None:
    tasks = [
        {"reason": "low_confidence", "created_at": "x", "id": 1},
        {"reason": "low_confidence", "created_at": "x", "id": 2},
        {"reason": "low_confidence", "created_at": "x", "id": 3},
    ]
    ordered = sort_queue(tasks)
    assert [t["id"] for t in ordered] == [1, 2, 3]


def test_sort_queue_does_not_mutate_input() -> None:
    tasks = [
        {"reason": "new_schema_term", "created_at": "b"},
        {"reason": "contradicts_existing", "created_at": "a"},
    ]
    original = list(tasks)
    sort_queue(tasks)
    assert tasks == original


def test_sort_queue_missing_created_at() -> None:
    tasks = [
        {"reason": "contradicts_existing"},
        {"reason": "low_confidence"},
    ]
    ordered = sort_queue(tasks)
    assert ordered[0]["reason"] == "contradicts_existing"


def test_sort_queue_unknown_reason_raises() -> None:
    with pytest.raises(ValueError):
        sort_queue([{"reason": "nope", "created_at": "a"}])


def test_review_reason_as_dict() -> None:
    assert ReviewReason("low_quality_ocr", 1).as_dict()["code"] == "low_quality_ocr"
    assert ReviewReason("low_quality_ocr", 1).as_dict() == {
        "code": "low_quality_ocr",
        "priority": 1,
    }


def test_review_reason_frozen() -> None:
    reason = ReviewReason("new_schema_term", 20)
    with pytest.raises(FrozenInstanceError):
        reason.code = "other"  # type: ignore[misc]
