"""Тесты валидатора тела решения ревью (§14.14).

Tests for the accept/reject/correct decision-body validator of
``POST /curation/review-queue/{task_id}`` and its map to a §12.3 curation action.
"""

from __future__ import annotations

import pytest
from api_gateway.curation_decision import (
    DECISIONS,
    ReviewDecision,
    parse_decision,
    to_curation_action,
)


def test_decisions_vocabulary() -> None:
    """DECISIONS — ровно {accept, reject, correct}, неизменяемый frozenset."""
    assert frozenset({"accept", "reject", "correct"}) == DECISIONS
    assert isinstance(DECISIONS, frozenset)


def test_accept_parses() -> None:
    """accept без corrected — валидно, corrected становится None."""
    d = parse_decision({"decision": "accept", "reason": "ok"})
    assert d.decision == "accept"
    assert d.corrected is None
    assert d.reason == "ok"


def test_correct_missing_corrected_raises() -> None:
    """correct без corrected — ValueError."""
    with pytest.raises(ValueError):
        parse_decision({"decision": "correct", "reason": "r"})


def test_correct_with_payload() -> None:
    """correct с непустым corrected — сохраняет payload."""
    d = parse_decision({"decision": "correct", "corrected": {"value": 5}, "reason": "r"})
    assert d.corrected == {"value": 5}
    assert d.decision == "correct"


def test_correct_empty_payload_raises() -> None:
    """correct с пустым corrected — ValueError."""
    with pytest.raises(ValueError):
        parse_decision({"decision": "correct", "corrected": {}, "reason": "r"})


def test_reject_blank_reason_raises() -> None:
    """reject с пустым reason — ValueError."""
    with pytest.raises(ValueError):
        parse_decision({"decision": "reject", "reason": ""})


def test_whitespace_reason_raises() -> None:
    """reason из одних пробелов — ValueError."""
    with pytest.raises(ValueError):
        parse_decision({"decision": "accept", "reason": "   "})


def test_bogus_decision_raises() -> None:
    """неизвестное decision — ValueError."""
    with pytest.raises(ValueError):
        parse_decision({"decision": "bogus", "reason": "r"})


def test_missing_decision_raises() -> None:
    """отсутствующее decision — ValueError."""
    with pytest.raises(ValueError):
        parse_decision({"reason": "r"})


def test_to_curation_action_reject() -> None:
    """reject отображается в 'reject'."""
    assert to_curation_action(parse_decision({"decision": "reject", "reason": "r"})) == "reject"


def test_to_curation_action_accept_and_correct() -> None:
    """accept→accept, correct→correct."""
    assert to_curation_action(parse_decision({"decision": "accept", "reason": "r"})) == "accept"
    corrected = parse_decision({"decision": "correct", "corrected": {"x": 1}, "reason": "r"})
    assert to_curation_action(corrected) == "correct"


def test_as_dict_keys() -> None:
    """as_dict содержит ровно {decision, corrected, reason}."""
    d = parse_decision({"decision": "correct", "corrected": {"value": 5}, "reason": "r"})
    assert set(d.as_dict().keys()) == {"decision", "corrected", "reason"}
    assert d.as_dict() == {"decision": "correct", "corrected": {"value": 5}, "reason": "r"}


def test_frozen_immutable() -> None:
    """ReviewDecision заморожен — присваивание падает."""
    d = ReviewDecision(decision="accept", corrected=None, reason="ok")
    with pytest.raises((AttributeError, TypeError)):
        d.decision = "reject"  # type: ignore[misc]
