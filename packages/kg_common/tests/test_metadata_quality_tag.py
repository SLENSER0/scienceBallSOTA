"""Tests for auto quality-tag from review-status aggregate — тесты (§10.11)."""

from __future__ import annotations

from kg_common.metadata.quality_tag import (
    TAG_PENDING,
    TAG_VERIFIED,
    QualityAssessment,
    assess_from_statuses,
    compute_quality,
)


def test_compute_quality_above_threshold_is_verified() -> None:
    result = compute_quality(8, 10)
    assert result.tag == "quality:verified"
    assert result.tag == TAG_VERIFIED
    assert result.ratio == 0.8
    assert result.accepted == 8
    assert result.total == 10


def test_compute_quality_below_threshold_is_pending() -> None:
    result = compute_quality(3, 10)
    assert result.tag == "quality:pending"
    assert result.ratio == 0.3


def test_compute_quality_empty_aggregate_is_pending_zero_ratio() -> None:
    result = compute_quality(0, 0)
    assert result.ratio == 0.0
    assert result.tag == "quality:pending"
    assert result.tag == TAG_PENDING


def test_compute_quality_ratio_equal_to_threshold_is_verified() -> None:
    # ratio == threshold (0.5) counts as verified (>=).
    result = compute_quality(5, 10, threshold=0.5)
    assert result.ratio == 0.5
    assert result.tag == "quality:verified"


def test_compute_quality_ratio_just_below_threshold_is_pending() -> None:
    result = compute_quality(4, 10, threshold=0.5)
    assert result.ratio == 0.4
    assert result.tag == "quality:pending"


def test_compute_quality_high_threshold_flips_to_pending() -> None:
    # 0.8 ratio but a stricter 0.9 bar -> pending.
    result = compute_quality(8, 10, threshold=0.9)
    assert result.tag == "quality:pending"


def test_assess_from_statuses_counts_accepted() -> None:
    result = assess_from_statuses(["accepted", "accepted", "pending"])
    assert result.accepted == 2
    assert result.total == 3
    # 2/3 ~= 0.6667 >= 0.5 -> verified.
    assert result.tag == "quality:verified"


def test_assess_from_statuses_half_accepted_is_verified() -> None:
    result = assess_from_statuses(["accepted", "accepted", "rejected", "rejected"])
    assert result.accepted == 2
    assert result.total == 4
    assert result.ratio == 0.5
    assert result.tag == "quality:verified"


def test_assess_from_statuses_empty_is_pending() -> None:
    result = assess_from_statuses([])
    assert result.total == 0
    assert result.accepted == 0
    assert result.ratio == 0.0
    assert result.tag == "quality:pending"


def test_assess_from_statuses_only_non_accepted_is_pending() -> None:
    result = assess_from_statuses(["pending", "rejected", "rejected"])
    assert result.accepted == 0
    assert result.ratio == 0.0
    assert result.tag == "quality:pending"


def test_quality_assessment_is_frozen() -> None:
    result = compute_quality(1, 2)
    try:
        result.tag = "quality:verified"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("QualityAssessment must be frozen")


def test_as_dict_round_trip() -> None:
    result = compute_quality(8, 10)
    assert result.as_dict() == {
        "total": 10,
        "accepted": 8,
        "ratio": 0.8,
        "tag": "quality:verified",
    }


def test_as_dict_reconstructs_equal_instance() -> None:
    result = compute_quality(3, 10)
    assert QualityAssessment(**result.as_dict()) == result
