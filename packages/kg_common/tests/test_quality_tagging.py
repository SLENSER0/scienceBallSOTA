"""Tests for §10.11 auto quality tagging (тег качества из ревью-свидетельств)."""

from __future__ import annotations

from kg_common.quality_tagging import (
    TAG_PENDING,
    TAG_VERIFIED,
    QualityAssessment,
    assess_quality,
)


def test_at_threshold_is_verified() -> None:
    # 8 accepted / 10 -> ratio 0.8 == threshold -> verified
    result = assess_quality(["accepted"] * 8 + ["pending"] * 2)
    assert result.tag == TAG_VERIFIED
    assert result.accepted_ratio == 0.8
    assert result.total == 10
    assert result.accepted == 8
    assert result.pending == 2


def test_below_threshold_is_pending() -> None:
    # 7 accepted / 10 -> ratio 0.7 < 0.8 -> pending
    result = assess_quality(["accepted"] * 7 + ["pending"] * 3)
    assert result.tag == TAG_PENDING
    assert result.accepted_ratio == 0.7


def test_empty_is_pending_with_zero_total() -> None:
    result = assess_quality([])
    assert result.tag == TAG_PENDING
    assert result.total == 0
    assert result.accepted == 0
    assert result.accepted_ratio == 0.0


def test_single_rejected() -> None:
    result = assess_quality(["rejected"])
    assert result.accepted == 0
    assert result.rejected == 1
    assert result.total == 1
    assert result.tag == TAG_PENDING


def test_unknown_status_ignored() -> None:
    result = assess_quality(["accepted", "accepted", "junk"])
    assert result.total == 2  # "junk" not counted
    assert result.accepted == 2
    assert result.tag == TAG_VERIFIED  # ratio 1.0 >= 0.8


def test_threshold_one_exact() -> None:
    result = assess_quality(["accepted"], threshold=1.0)
    assert result.tag == TAG_VERIFIED
    assert result.accepted_ratio == 1.0


def test_half_ratio() -> None:
    result = assess_quality(["accepted", "pending"])
    assert result.accepted_ratio == 0.5
    assert result.tag == TAG_PENDING


def test_threshold_one_below() -> None:
    # ratio 0.5 < 1.0 -> pending even with an accepted present
    result = assess_quality(["accepted", "rejected"], threshold=1.0)
    assert result.tag == TAG_PENDING
    assert result.accepted_ratio == 0.5


def test_as_dict_round_trip() -> None:
    result = assess_quality(["accepted", "pending", "rejected"])
    payload = result.as_dict()
    assert payload == {
        "total": 3,
        "accepted": 1,
        "pending": 1,
        "rejected": 1,
        "accepted_ratio": round(1 / 3, 6),
        "tag": TAG_PENDING,
    }
    assert "tag" in payload
    # rebuild the frozen dataclass from its own dict
    assert QualityAssessment(**payload) == result
