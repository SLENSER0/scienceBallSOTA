"""Tests for the ``ambiguous_er`` review rule (§16.5).

Тесты правила ``ambiguous_er`` (§16.5).
"""

from __future__ import annotations

import pytest

from kg_extractors.ambiguous_er_rule import (
    AmbiguousErFinding,
    detect_ambiguous,
    scan,
)


def _candidate(matches, *, decision=None, cid="c1", mentions=("Fe", "iron")):
    """Build a Splink-style ER output mapping for tests (§16.5)."""
    out: dict = {"candidate_id": cid, "mentions": list(mentions), "matches": matches}
    if decision is not None:
        out["decision"] = decision
    return out


def test_clear_winner_returns_none() -> None:
    """(1) 0.90 vs 0.55 with threshold 0.1 -> no ambiguity (§16.5)."""
    cand = _candidate(
        [
            {"entity_id": "E1", "match_probability": 0.90},
            {"entity_id": "E2", "match_probability": 0.55},
        ]
    )
    assert detect_ambiguous(cand, margin_threshold=0.1) is None


def test_close_margin_produces_finding() -> None:
    """(2) 0.61 vs 0.60 -> finding, margin ~0.01, canonical == top entity_id (§16.5)."""
    cand = _candidate(
        [
            {"entity_id": "E1", "match_probability": 0.61},
            {"entity_id": "E2", "match_probability": 0.60},
        ]
    )
    finding = detect_ambiguous(cand, margin_threshold=0.1)
    assert finding is not None
    assert finding.margin == pytest.approx(0.01)
    assert finding.proposed_canonical == "E1"


def test_review_needed_decision_forces_finding() -> None:
    """(3) decision == 'review_needed' emits a finding regardless of margin (§16.5)."""
    cand = _candidate(
        [
            {"entity_id": "E1", "match_probability": 0.90},
            {"entity_id": "E2", "match_probability": 0.10},
        ],
        decision="review_needed",
    )
    finding = detect_ambiguous(cand, margin_threshold=0.1)
    assert finding is not None
    assert finding.proposed_canonical == "E1"


def test_finding_scores() -> None:
    """(4) top_score / runner_up_score reflect the sorted match probabilities (§16.5)."""
    cand = _candidate(
        [
            {"entity_id": "E1", "match_probability": 0.61},
            {"entity_id": "E2", "match_probability": 0.60},
        ]
    )
    finding = detect_ambiguous(cand, margin_threshold=0.1)
    assert finding is not None
    assert finding.top_score == 0.61
    assert finding.runner_up_score == 0.60


def test_as_dict_payload() -> None:
    """(5) as_dict() carries task_type and a 2-item candidates list (§16.5)."""
    cand = _candidate(
        [
            {"entity_id": "E1", "match_probability": 0.61},
            {"entity_id": "E2", "match_probability": 0.60},
        ]
    )
    finding = detect_ambiguous(cand, margin_threshold=0.1)
    assert finding is not None
    payload = finding.as_dict()
    assert payload["task_type"] == "ambiguous_er"
    assert isinstance(payload["candidates"], list)
    assert len(payload["candidates"]) == 2


def test_single_match_returns_none() -> None:
    """(6) a single-match candidate has no runner-up ambiguity (§16.5)."""
    cand = _candidate([{"entity_id": "E1", "match_probability": 0.61}])
    assert detect_ambiguous(cand, margin_threshold=0.1) is None


def test_scan_over_clear_and_tie() -> None:
    """(7) scan([clear, tie]) yields exactly one finding (§16.5)."""
    clear = _candidate(
        [
            {"entity_id": "E1", "match_probability": 0.90},
            {"entity_id": "E2", "match_probability": 0.55},
        ],
        cid="clear",
    )
    tie = _candidate(
        [
            {"entity_id": "E3", "match_probability": 0.61},
            {"entity_id": "E4", "match_probability": 0.60},
        ],
        cid="tie",
    )
    findings = scan([clear, tie], margin_threshold=0.1)
    assert len(findings) == 1
    assert isinstance(findings[0], AmbiguousErFinding)
    assert findings[0].candidate_id == "tie"
