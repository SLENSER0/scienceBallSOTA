"""Tests for §7.5 Node 3 entity-resolution clarify gate / hand-checkable cases."""

from __future__ import annotations

from agent_service.resolution_clarify import ClarifyDecision, decide_resolution


def _cand(cid: str, conf: float) -> dict[str, object]:
    return {"canonical_id": cid, "confidence": conf}


def test_ambiguous_critical_asks_clarification() -> None:
    # (1) near-tie 0.55/0.52 (gap 0.03 < 0.1) + critical -> clarify.
    cands = [_cand("A", 0.55), _cand("B", 0.52)]
    decision = decide_resolution(cands, critical=True)
    assert decision.should_clarify is True


def test_ambiguous_non_critical_does_not_clarify() -> None:
    # (2) same near-tie but not critical -> ambiguity does not block the answer.
    cands = [_cand("A", 0.55), _cand("B", 0.52)]
    decision = decide_resolution(cands, critical=False)
    assert decision.should_clarify is False


def test_clear_winner_critical_does_not_clarify() -> None:
    # (3) gap 0.6 >= margin -> a clear winner, no clarification even if critical.
    cands = [_cand("A", 0.9), _cand("B", 0.3)]
    decision = decide_resolution(cands, critical=True)
    assert decision.should_clarify is False


def test_low_top_confidence_flags_review() -> None:
    # (4) top 0.4 < low_conf 0.5 -> review with the fixed gap_type.
    cands = [_cand("A", 0.4), _cand("B", 0.2)]
    decision = decide_resolution(cands, critical=False)
    assert decision.should_review is True
    assert decision.gap_type == "low_confidence_entity_resolution"


def test_high_top_confidence_no_review() -> None:
    # (5) top 0.8 >= low_conf -> no review, no gap_type.
    cands = [_cand("A", 0.8), _cand("B", 0.1)]
    decision = decide_resolution(cands, critical=False)
    assert decision.should_review is False
    assert decision.gap_type is None


def test_best_candidate_is_max_confidence() -> None:
    # (6) unsorted input; best_candidate must be the max-confidence entry.
    cands = [_cand("A", 0.3), _cand("B", 0.9), _cand("C", 0.5)]
    decision = decide_resolution(cands, critical=True)
    assert decision.best_candidate == {"canonical_id": "B", "confidence": 0.9}


def test_empty_candidates() -> None:
    # (7) nothing to resolve -> no clarify, no best candidate.
    decision = decide_resolution([], critical=True)
    assert decision.should_clarify is False
    assert decision.best_candidate is None


def test_as_dict_exposes_all_keys() -> None:
    # (8) as_dict() surfaces exactly the four fields.
    decision = decide_resolution([_cand("A", 0.55), _cand("B", 0.52)], critical=True)
    payload = decision.as_dict()
    assert set(payload) == {
        "should_clarify",
        "should_review",
        "gap_type",
        "best_candidate",
    }
    assert isinstance(decision, ClarifyDecision)
