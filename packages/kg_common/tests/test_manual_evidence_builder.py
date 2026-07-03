"""Tests for :mod:`kg_common.storage.manual_evidence_builder` — action ``manual_evidence`` (§16.6).

Hand-checkable assertions covering the fabricated verified Evidence, its SUPPORTS
edge, deterministic id derivation, explicit-id passthrough, blank-input validation
and the nested :meth:`ManualEvidence.as_dict` view.
"""

from __future__ import annotations

from kg_common.storage.manual_evidence_builder import (
    MANUAL_ID_PREFIX,
    SUPPORTS_REL_TYPE,
    build_manual_evidence,
    validate_inputs,
)

TARGET = "node:prop:42"
TEXT = "The measured band gap is 1.1 eV."
ACTOR = "curator:alice"
NOW = "2026-07-03T12:00:00Z"


def test_evidence_is_verified_manual_source() -> None:
    """(1) source_type=='manual' and verified is True (§16.6)."""
    result = build_manual_evidence(TARGET, TEXT, ACTOR, NOW)
    assert result.evidence["source_type"] == "manual"
    assert result.evidence["verified"] is True
    assert result.evidence["extractor"] == "manual"
    assert result.evidence["text"] == TEXT


def test_review_status_accepted_and_reviewer() -> None:
    """(2) review_status=='accepted' and reviewed_by==actor (§16.6)."""
    result = build_manual_evidence(TARGET, TEXT, ACTOR, NOW)
    assert result.evidence["review_status"] == "accepted"
    assert result.evidence["reviewed_by"] == ACTOR
    assert result.evidence["reviewed_at"] == NOW


def test_edge_links_evidence_supports_target() -> None:
    """(3) edge == {src: evidence_id, rel_type: 'SUPPORTS', dst: target_id} (§16.6)."""
    result = build_manual_evidence(TARGET, TEXT, ACTOR, NOW, evidence_id="ev:x")
    assert result.edge == {
        "src": "ev:x",
        "rel_type": SUPPORTS_REL_TYPE,
        "dst": TARGET,
    }


def test_default_id_deterministic_and_prefixed() -> None:
    """(4) omitting evidence_id yields a stable 'ev:manual:'-prefixed id (§16.6)."""
    first = build_manual_evidence(TARGET, TEXT, ACTOR, NOW)
    second = build_manual_evidence(TARGET, TEXT, "curator:bob", "2099-01-01T00:00:00Z")
    ev_id = first.evidence["id"]
    assert isinstance(ev_id, str)
    assert ev_id.startswith(MANUAL_ID_PREFIX)
    # Stable across two calls with the same target_id + text (actor/now irrelevant).
    assert first.evidence["id"] == second.evidence["id"]
    # Different text → different id.
    other = build_manual_evidence(TARGET, TEXT + "!", ACTOR, NOW)
    assert other.evidence["id"] != ev_id


def test_blank_text_returns_errors() -> None:
    """(5) blank text → validate_inputs returns a non-empty error list (§16.6)."""
    assert validate_inputs(TARGET, "   ") != []
    assert validate_inputs(TARGET, "") != []
    assert validate_inputs("", TEXT) != []
    # Valid inputs → no errors.
    assert validate_inputs(TARGET, TEXT) == []


def test_explicit_evidence_id_used_verbatim() -> None:
    """(6) explicit evidence_id is used verbatim (§16.6)."""
    result = build_manual_evidence(TARGET, TEXT, ACTOR, NOW, evidence_id="ev:custom:99")
    assert result.evidence["id"] == "ev:custom:99"
    assert result.edge["src"] == "ev:custom:99"


def test_as_dict_nests_evidence_and_edge() -> None:
    """(7) as_dict nests evidence and edge (§16.6)."""
    result = build_manual_evidence(TARGET, TEXT, ACTOR, NOW)
    payload = result.as_dict()
    assert payload == {"evidence": result.evidence, "edge": result.edge}
    assert payload["evidence"]["id"] == result.edge["src"]
