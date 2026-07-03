"""Tests for §6.15 extraction review routing — hand-checked verdicts.

Confidence bands use :data:`DEFAULT_THRESHOLDS` (auto_accept_at=0.85,
reject_at=0.2): 0.9 → auto_accept, 0.1 → reject, 0.5 → review. Escalation flags
(нет единицы / вне диапазона / конфликт / OCR) force review regardless of score.
"""

from __future__ import annotations

from kg_extractors.review_routing import (
    ACTION_AUTO_ACCEPT,
    ACTION_REJECT,
    ACTION_REVIEW,
    DEFAULT_THRESHOLDS,
    REASON_MID_CONFIDENCE,
    REASON_MISSING_UNIT,
    REASON_OUT_OF_RANGE,
    BatchRouting,
    ReviewDecision,
    route_batch,
    route_extraction,
)


def test_default_thresholds_values() -> None:
    """DEFAULT_THRESHOLDS matches the §6.15 policy (0.85 / 0.2)."""
    assert DEFAULT_THRESHOLDS == {"auto_accept_at": 0.85, "reject_at": 0.2}


def test_high_confidence_clean_auto_accept() -> None:
    """0.9 confidence, no flags → auto_accept with no reasons (§6.15)."""
    d = route_extraction({"confidence": 0.9, "unit": "MPa", "value": 500})
    assert isinstance(d, ReviewDecision)
    assert d.action == ACTION_AUTO_ACCEPT
    assert d.reasons == []
    assert d.escalated is False
    # priority = 1 - 0.9 = 0.1 (hand-checked).
    assert d.priority == 0.1


def test_low_confidence_clean_reject() -> None:
    """0.1 confidence, no flags → reject (§6.15)."""
    d = route_extraction({"confidence": 0.1, "unit": "MPa", "value": 500})
    assert d.action == ACTION_REJECT
    assert "low_confidence" in d.reasons
    # priority = 1 - 0.1 = 0.9 (hand-checked).
    assert d.priority == 0.9


def test_mid_confidence_clean_review() -> None:
    """0.5 confidence, no flags → review (mid band) (§6.15)."""
    d = route_extraction({"confidence": 0.5, "unit": "MPa", "value": 500})
    assert d.action == ACTION_REVIEW
    assert d.reasons == [REASON_MID_CONFIDENCE]
    assert d.needs_review is True
    # priority = 1 - 0.5 = 0.5 (hand-checked).
    assert d.priority == 0.5


def test_missing_unit_escalates_mid_confidence_with_reason() -> None:
    """A value with no unit at mid confidence → review carrying missing_unit (§7.5)."""
    d = route_extraction({"confidence": 0.5, "value": 500})
    assert d.action == ACTION_REVIEW
    assert REASON_MISSING_UNIT in d.reasons
    assert d.escalated is True


def test_out_of_range_forces_review_at_high_confidence() -> None:
    """out_of_range flag forces review even though 0.95 would auto-accept (§7.7)."""
    d = route_extraction(
        {"confidence": 0.95, "unit": "MPa", "value": 999999, "flags": ["out_of_range"]}
    )
    assert d.action == ACTION_REVIEW
    assert REASON_OUT_OF_RANGE in d.reasons
    assert d.escalated is True


def test_conflicting_flag_forces_review_at_high_confidence() -> None:
    """conflicting flag (extractors disagree) forces review at 0.9 (§6.13)."""
    d = route_extraction({"confidence": 0.9, "unit": "MPa", "value": 500, "flags": ["conflicting"]})
    assert d.action == ACTION_REVIEW
    assert "conflicting" in d.reasons


def test_low_ocr_flag_forces_review_at_high_confidence() -> None:
    """low_ocr flag (низкое качество OCR) forces review at 0.88 (§5)."""
    d = route_extraction({"confidence": 0.88, "unit": "MPa", "value": 500, "flags": ["low_ocr"]})
    assert d.action == ACTION_REVIEW
    assert "low_ocr" in d.reasons


def test_priority_higher_for_lower_confidence() -> None:
    """Lower confidence → higher review-queue priority (§6.15)."""
    low = route_extraction({"confidence": 0.3, "unit": "MPa", "value": 500})
    high = route_extraction({"confidence": 0.7, "unit": "MPa", "value": 500})
    assert low.priority > high.priority
    # hand-checked: 1 - 0.3 = 0.7  vs  1 - 0.7 = 0.3.
    assert low.priority == 0.7
    assert high.priority == 0.3


def test_route_batch_buckets_and_counts_sum() -> None:
    """route_batch partitions items; counts sum to the item total (§6.15)."""
    items = [
        {"confidence": 0.9, "unit": "MPa", "value": 500},  # auto_accept
        {"confidence": 0.95, "unit": "MPa", "value": 500},  # auto_accept
        {"confidence": 0.5, "unit": "MPa", "value": 500},  # review (mid)
        {"confidence": 0.1, "unit": "MPa", "value": 500},  # reject
        {"confidence": 0.95, "flags": ["out_of_range"], "value": 9e9},  # review (esc)
    ]
    result = route_batch(items)
    assert isinstance(result, BatchRouting)
    assert result.counts == {ACTION_AUTO_ACCEPT: 2, ACTION_REVIEW: 2, ACTION_REJECT: 1}
    assert len(result.auto_accept) == 2
    assert len(result.review) == 2
    assert len(result.reject) == 1
    # counts sum to the number of items, buckets partition the input.
    assert sum(result.counts.values()) == len(items)
    assert result.total == len(items)


def test_route_batch_review_sorted_by_priority_descending() -> None:
    """review bucket leads with the highest-priority (lowest-confidence) fact (§6.15)."""
    items = [
        {"confidence": 0.95, "flags": ["out_of_range"], "value": 9e9},  # priority ~0.1
        {"confidence": 0.5, "unit": "MPa", "value": 500},  # priority 0.5
    ]
    result = route_batch(items)
    assert len(result.review) == 2
    # 0.5-confidence item (priority 0.5) sorts ahead of the escalated 0.95 item.
    assert result.review[0]["confidence"] == 0.5
    assert result.review[1]["confidence"] == 0.95


def test_custom_thresholds_respected() -> None:
    """Custom thresholds flip verdicts vs the defaults (§6.15)."""
    custom = {"auto_accept_at": 0.6, "reject_at": 0.4}
    # 0.7 auto-accepts under 0.6 but only reviews under the 0.85 default.
    accept = route_extraction({"confidence": 0.7, "unit": "MPa", "value": 500}, thresholds=custom)
    assert accept.action == ACTION_AUTO_ACCEPT
    assert (
        route_extraction({"confidence": 0.7, "unit": "MPa", "value": 500}).action == ACTION_REVIEW
    )
    # 0.3 rejects under reject_at=0.4 but reviews under the 0.2 default.
    reject = route_extraction({"confidence": 0.3, "unit": "MPa", "value": 500}, thresholds=custom)
    assert reject.action == ACTION_REJECT
    assert (
        route_extraction({"confidence": 0.3, "unit": "MPa", "value": 500}).action == ACTION_REVIEW
    )


def test_partial_custom_thresholds_merge_over_defaults() -> None:
    """A partial thresholds dict overrides only the given key (§6.15)."""
    # Only lower auto_accept_at; reject_at stays at the 0.2 default.
    d = route_extraction(
        {"confidence": 0.7, "unit": "MPa", "value": 500}, thresholds={"auto_accept_at": 0.65}
    )
    assert d.action == ACTION_AUTO_ACCEPT


def test_as_dict_exposes_all_fields() -> None:
    """ReviewDecision.as_dict() carries the full field set (§6.15)."""
    d = route_extraction({"confidence": 0.5, "value": 500})
    out = d.as_dict()
    assert set(out) == {"action", "priority", "reasons", "needs_review", "escalated"}
    assert out["action"] == ACTION_REVIEW
    assert REASON_MISSING_UNIT in out["reasons"]
    assert out["escalated"] is True
