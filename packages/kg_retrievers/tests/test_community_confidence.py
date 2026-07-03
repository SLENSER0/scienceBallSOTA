"""Tests for community-report confidence propagation (§11.11)."""

from __future__ import annotations

from kg_retrievers.community_confidence import CommunityConfidence, aggregate_confidence


def test_mean_confidence_and_all_accepted() -> None:
    """Two accepted members [0.4, 0.6] average to 0.5 and stay accepted."""
    result = aggregate_confidence("c1", [0.4, 0.6], ["accepted", "accepted"])
    assert result.confidence == 0.5
    assert result.review_status == "accepted"
    assert result.n_members == 2


def test_single_rejected_dominates() -> None:
    """One 'rejected' among accepted members forces a rejected verdict."""
    result = aggregate_confidence("c1", [0.9, 0.8, 0.7], ["accepted", "rejected", "accepted"])
    assert result.review_status == "rejected"


def test_mixed_accepted_pending_is_pending() -> None:
    """A mix of accepted and pending (no rejected) yields pending."""
    result = aggregate_confidence("c1", [0.9, 0.9], ["accepted", "pending"])
    assert result.review_status == "pending"


def test_empty_members() -> None:
    """No members -> 0.0 confidence, zero members, pending status."""
    result = aggregate_confidence("c1", [], [])
    assert result.confidence == 0.0
    assert result.n_members == 0
    assert result.review_status == "pending"


def test_n_supported_at_threshold() -> None:
    """At threshold 0.5, only 0.6 (>=0.5) counts as supported for [0.4, 0.6]."""
    result = aggregate_confidence("c1", [0.4, 0.6], ["accepted", "accepted"], 0.5)
    assert result.n_supported == 1


def test_n_members_matches_input_length() -> None:
    """n_members mirrors len(member_confidences)."""
    confidences = [0.1, 0.2, 0.3, 0.4]
    result = aggregate_confidence("c1", confidences, ["pending"] * 4)
    assert result.n_members == len(confidences)


def test_as_dict_roundtrip() -> None:
    """as_dict() exposes all fields including community_id."""
    result = aggregate_confidence("c1", [0.4, 0.6], ["accepted", "accepted"])
    data = result.as_dict()
    assert data["community_id"] == "c1"
    assert data["confidence"] == 0.5
    assert data["review_status"] == "accepted"
    assert data["n_supported"] == 1
    assert data["n_members"] == 2


def test_threshold_boundary_and_frozen() -> None:
    """Exactly-at-threshold counts as supported; the dataclass is frozen."""
    result = aggregate_confidence("c1", [0.5, 0.5], ["accepted", "accepted"], 0.5)
    assert result.n_supported == 2
    assert isinstance(result, CommunityConfidence)
    try:
        result.confidence = 0.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("CommunityConfidence should be frozen")
