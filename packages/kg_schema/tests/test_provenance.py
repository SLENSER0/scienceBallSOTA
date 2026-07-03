"""Tests for provenance-completeness validation (§3.7)."""

from __future__ import annotations

from typing import Any

from kg_schema.provenance import (
    REQUIRED_PROVENANCE,
    ProvenanceCheck,
    provenance_report,
    validate_provenance,
)


def _good_measurement() -> dict[str, Any]:
    """A factual Measurement carrying every required provenance field (§3.7)."""
    return {
        "label": "Measurement",
        "id": "measurement:m1",
        "name": "Cu recovery 92%",
        "extractor_run_id": "run:2026-07-03T10:00",
        "schema_version": "1.4.0",
        "created_at": "2026-07-03T10:00:00Z",
        "review_status": "accepted",
        "confidence": 0.9,
    }


def test_required_provenance_fields() -> None:
    # The §3.7 obligation is exactly these three fields, in order.
    assert REQUIRED_PROVENANCE == ("extractor_run_id", "schema_version", "created_at")


def test_complete_measurement_passes() -> None:
    check = validate_provenance(_good_measurement())
    assert isinstance(check, ProvenanceCheck)
    assert check.complete is True
    assert check.missing == []
    assert check.is_factual is True
    d = check.as_dict()
    assert d["complete"] is True
    assert d["missing"] == []
    assert d["label"] == "Measurement"


def test_missing_created_at_flagged() -> None:
    node = _good_measurement()
    del node["created_at"]
    check = validate_provenance(node)
    # A factual node lacking a required field is incomplete, and the specific
    # missing field is named.
    assert check.complete is False
    assert check.missing == ["created_at"]
    assert check.is_factual is True


def test_non_factual_chunk_not_required() -> None:
    # A Chunk is not a factual node -> no provenance obligation, so it is
    # trivially complete even with no provenance fields at all.
    check = validate_provenance({"label": "Chunk", "id": "chunk:c1", "text": "hi"})
    assert check.is_factual is False
    assert check.complete is True
    assert check.missing == []


def test_is_factual_set_correctly() -> None:
    assert validate_provenance({"label": "Measurement"}).is_factual is True
    assert validate_provenance({"label": "Claim"}).is_factual is True
    assert validate_provenance({"label": "KnowledgeClaim"}).is_factual is True
    assert validate_provenance({"label": "Document"}).is_factual is False
    assert validate_provenance({"label": "Chunk"}).is_factual is False
    # Unlabelled nodes are treated as non-factual.
    assert validate_provenance({}).is_factual is False


def test_curation_signals_noted() -> None:
    # review_status / confidence are *noted* but never affect completeness.
    with_signals = validate_provenance(_good_measurement())
    assert with_signals.has_review_status is True
    assert with_signals.has_confidence is True

    bare = _good_measurement()
    del bare["review_status"]
    del bare["confidence"]
    check = validate_provenance(bare)
    assert check.has_review_status is False
    assert check.has_confidence is False
    # Still complete: curation signals are not part of REQUIRED_PROVENANCE.
    assert check.complete is True


def test_evidence_link_flag_surfaced() -> None:
    linked = _good_measurement()
    linked["_has_evidence"] = True
    assert validate_provenance(linked).has_evidence_link is True
    # Absent flag defaults to False.
    assert validate_provenance(_good_measurement()).has_evidence_link is False


def test_report_aggregates() -> None:
    complete_m = _good_measurement()  # complete

    no_created = _good_measurement()
    del no_created["created_at"]  # missing created_at

    thin_claim = {
        "label": "Claim",
        "id": "claim:c1",
        "created_at": "2026-07-03T00:00:00Z",
    }  # missing extractor_run_id + schema_version

    chunk = {"label": "Chunk", "id": "chunk:c1"}  # non-factual -> complete

    report = provenance_report([complete_m, no_created, thin_claim, chunk])
    assert report["total"] == 4
    assert report["complete"] == 2  # complete_m + chunk
    assert report["incomplete"] == 2  # no_created + thin_claim
    assert report["by_missing_field"] == {
        "created_at": 1,
        "extractor_run_id": 1,
        "schema_version": 1,
    }


def test_empty_report_is_zero() -> None:
    report = provenance_report([])
    assert report == {
        "total": 0,
        "complete": 0,
        "incomplete": 0,
        "by_missing_field": {},
    }
