"""Tests for evidence-first custom aspects — тесты доказательных аспектов (§10.3)."""

from __future__ import annotations

import pytest

from kg_common.metadata.evidence_aspects import (
    EvidenceAspect,
    from_evidence,
    merge_aspects,
    to_custom_properties,
)


def test_confidence_formatted_two_decimals() -> None:
    """``confidence`` renders with exactly two decimal places."""
    props = to_custom_properties(EvidenceAspect(0.9, "accepted"))
    assert props["confidence"] == "0.90"


def test_blank_optional_fields_dropped() -> None:
    """An empty ``model`` never appears as a ``customProperties`` key."""
    props = to_custom_properties(EvidenceAspect(0.9, "accepted"))
    assert "model" not in props
    assert "extractor" not in props
    assert "extractor_run_id" not in props
    assert "mlflow_run_id" not in props


def test_review_status_carried_through() -> None:
    """``review_status`` is copied verbatim into the flat map."""
    props = to_custom_properties(EvidenceAspect(0.9, "accepted"))
    assert props["review_status"] == "accepted"


def test_non_empty_optional_fields_kept_and_stringified() -> None:
    """Non-blank provenance fields survive and are stringified."""
    aspect = EvidenceAspect(
        0.42,
        "pending",
        extractor="ner-v2",
        model="qwen",
        extractor_run_id="r7",
        mlflow_run_id="mlf9",
    )
    props = to_custom_properties(aspect)
    assert props == {
        "confidence": "0.42",
        "review_status": "pending",
        "extractor": "ner-v2",
        "model": "qwen",
        "extractor_run_id": "r7",
        "mlflow_run_id": "mlf9",
    }


def test_whitespace_only_field_treated_as_absent() -> None:
    """A whitespace-only optional field is dropped like an empty one."""
    props = to_custom_properties(EvidenceAspect(0.5, "pending", model="   "))
    assert "model" not in props


def test_confidence_above_one_rejected() -> None:
    """A confidence above 1.0 is out of range and raises ``ValueError``."""
    with pytest.raises(ValueError):
        EvidenceAspect(1.5, "accepted")


def test_confidence_below_zero_rejected() -> None:
    """A negative confidence is out of range and raises ``ValueError``."""
    with pytest.raises(ValueError):
        EvidenceAspect(-0.1, "accepted")


def test_confidence_bounds_inclusive() -> None:
    """The bounds 0.0 and 1.0 are both accepted."""
    assert EvidenceAspect(0.0, "pending").confidence == 0.0
    assert EvidenceAspect(1.0, "accepted").confidence == 1.0


def test_from_evidence_reads_optional_field() -> None:
    """``from_evidence`` picks up a present optional field."""
    aspect = from_evidence({"confidence": 0.5, "review_status": "pending", "model": "m"})
    assert aspect.model == "m"
    assert aspect.confidence == 0.5
    assert aspect.review_status == "pending"


def test_from_evidence_ignores_unknown_keys() -> None:
    """Unknown evidence keys are silently ignored."""
    aspect = from_evidence({"confidence": 0.3, "review_status": "rejected", "junk": 1})
    assert aspect == EvidenceAspect(0.3, "rejected")


def test_from_evidence_defaults_when_missing() -> None:
    """Missing keys fall back to safe defaults."""
    aspect = from_evidence({})
    assert aspect == EvidenceAspect(0.0, "")


def test_merge_prefers_b_non_empty_field() -> None:
    """``b``'s non-empty ``model`` overrides ``a``'s."""
    merged = merge_aspects(
        EvidenceAspect(0.5, "pending", model="a"),
        EvidenceAspect(0.5, "pending", model="b"),
    )
    assert merged.model == "b"


def test_merge_keeps_a_when_b_field_empty() -> None:
    """``a``'s ``model`` is kept when ``b`` leaves it empty."""
    merged = merge_aspects(
        EvidenceAspect(0.5, "pending", model="a"),
        EvidenceAspect(0.5, "pending"),
    )
    assert merged.model == "a"


def test_merge_takes_b_confidence_and_status() -> None:
    """``confidence`` and ``review_status`` always come from ``b``."""
    merged = merge_aspects(
        EvidenceAspect(0.1, "pending", extractor="e1"),
        EvidenceAspect(0.9, "accepted"),
    )
    assert merged.confidence == 0.9
    assert merged.review_status == "accepted"
    assert merged.extractor == "e1"


def test_from_evidence_round_trips_as_dict() -> None:
    """``EvidenceAspect.from_evidence(a.as_dict())`` reconstructs ``a``."""
    aspect = EvidenceAspect(
        0.73,
        "accepted",
        extractor="ner",
        model="qwen",
        extractor_run_id="r1",
        mlflow_run_id="m1",
    )
    restored = EvidenceAspect.from_evidence(aspect.as_dict())
    assert restored == aspect
    assert restored.as_dict() == aspect.as_dict()


def test_aspect_is_frozen() -> None:
    """:class:`EvidenceAspect` is immutable."""
    aspect = EvidenceAspect(0.5, "pending")
    with pytest.raises((AttributeError, TypeError)):
        aspect.model = "x"  # type: ignore[misc]
