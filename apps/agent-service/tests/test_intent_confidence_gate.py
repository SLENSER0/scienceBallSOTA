"""Tests for §13.8 intent confidence gate — hand-checked decisions."""

from __future__ import annotations

from agent_service.intent_classifier import IntentClass
from agent_service.intent_confidence_gate import GateDecision, gate_intent


def _ic(query_type: str, confidence: float) -> IntentClass:
    """Build an ``IntentClass`` with a trivial signal list."""
    return IntentClass(query_type=query_type, confidence=confidence, signals=[])


def test_high_confidence_no_runner_up_proceeds() -> None:
    # (1) 0.9, no runner-up -> proceed.
    d = gate_intent(_ic("numeric", 0.9))
    assert d.action == "proceed"
    assert d.reason == "proceed"


def test_low_confidence_routes_schema_help() -> None:
    # (2) 0.2 < low(0.35) -> schema_help / low_confidence.
    d = gate_intent(_ic("structured", 0.2))
    assert d.action == "schema_help"
    assert d.reason == "low_confidence"


def test_near_tie_routes_clarify() -> None:
    # (3) 0.5 vs 0.45, margin 0.05 < 0.1 -> clarify / near_tie.
    d = gate_intent(_ic("numeric", 0.5), _ic("comparison", 0.45))
    assert d.action == "clarify"
    assert d.reason == "near_tie"


def test_clear_winner_over_runner_up_proceeds() -> None:
    # (4) 0.8 vs 0.4, margin 0.4 >= 0.1 -> proceed.
    d = gate_intent(_ic("numeric", 0.8), _ic("comparison", 0.4))
    assert d.action == "proceed"
    assert d.reason == "proceed"


def test_low_confidence_precedes_near_tie() -> None:
    # (5) 0.3 < low, even with a near-tie runner-up 0.28 -> schema_help wins.
    d = gate_intent(_ic("numeric", 0.3), _ic("comparison", 0.28))
    assert d.action == "schema_help"
    assert d.reason == "low_confidence"


def test_intent_echoes_primary_query_type() -> None:
    # (6) intent == primary.query_type.
    d = gate_intent(_ic("geography", 0.9))
    assert d.intent == "geography"
    assert d.confidence == 0.9


def test_as_dict_carries_all_fields() -> None:
    # (7) as_dict has all four fields.
    d = gate_intent(_ic("temporal", 0.5), _ic("numeric", 0.48))
    assert d.as_dict() == {
        "action": "clarify",
        "intent": "temporal",
        "confidence": 0.5,
        "reason": "near_tie",
    }
    assert isinstance(d, GateDecision)


def test_custom_thresholds_honoured() -> None:
    # (8) custom low/tie_margin change the outcome.
    # 0.5 would proceed at default low=0.35, but low=0.6 -> schema_help.
    d_low = gate_intent(_ic("numeric", 0.5), low=0.6)
    assert d_low.action == "schema_help"
    # 0.8 vs 0.4 (margin 0.4) proceeds by default, but tie_margin=0.5 -> clarify.
    d_tie = gate_intent(_ic("numeric", 0.8), _ic("comparison", 0.4), tie_margin=0.5)
    assert d_tie.action == "clarify"
    assert d_tie.reason == "near_tie"
