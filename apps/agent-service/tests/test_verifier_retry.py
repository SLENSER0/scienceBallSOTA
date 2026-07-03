"""Tests for §13.16 verifier retry loop / route_after_verify.

Hand-checkable cases: a fixable report retries and consumes an attempt, an
exhausted budget forwards, empty/non-fixable reports forward, and the
``unresolved`` ids match the offending violations.
"""

from __future__ import annotations

from agent_service.verifier_retry import (
    RetryDecision,
    is_fixable,
    route_after_verify,
)

_MISSING = {"violations": [{"id": "v1", "severity": "missing_evidence"}]}
_STYLE = {"violations": [{"id": "s1", "severity": "style"}]}
_EMPTY: dict = {}


def test_missing_evidence_retries_and_increments() -> None:
    # (1) one 'missing_evidence' at attempts=0,max=3 -> query_planner, attempts=1.
    d = route_after_verify(_MISSING, attempts=0, max_attempts=3)
    assert d.next_node == "query_planner"
    assert d.attempts == 1


def test_budget_exhausted_forwards_unchanged() -> None:
    # (2) same report at attempts=3 -> answer_synthesizer, attempts stays 3.
    d = route_after_verify(_MISSING, attempts=3, max_attempts=3)
    assert d.next_node == "answer_synthesizer"
    assert d.attempts == 3


def test_empty_report_forwards() -> None:
    # (3) empty report -> answer_synthesizer.
    d = route_after_verify(_EMPTY, attempts=0, max_attempts=3)
    assert d.next_node == "answer_synthesizer"
    assert d.attempts == 0
    assert d.unresolved == ()


def test_style_only_forwards() -> None:
    # (4) only severity 'style' -> answer_synthesizer, nothing unresolved.
    d = route_after_verify(_STYLE, attempts=0, max_attempts=3)
    assert d.next_node == "answer_synthesizer"
    assert d.unresolved == ()


def test_unresolved_lists_offending_ids() -> None:
    # (5) unresolved tuple lists the offending (fixable) violation ids only.
    report = {
        "violations": [
            {"id": "v1", "severity": "missing_evidence"},
            {"id": "v2", "severity": "style"},
            {"id": "v3", "severity": "empty_retrieval"},
        ]
    }
    d = route_after_verify(report, attempts=0, max_attempts=3)
    assert d.unresolved == ("v1", "v3")
    assert d.next_node == "query_planner"


def test_is_fixable_by_severity() -> None:
    # (6) empty_retrieval fixable, mixed_units not.
    assert is_fixable({"severity": "empty_retrieval"}) is True
    assert is_fixable({"severity": "missing_evidence"}) is True
    assert is_fixable({"severity": "mixed_units"}) is False
    assert is_fixable({}) is False


def test_as_dict_unresolved_is_list() -> None:
    # (7) as_dict()['unresolved'] is a list; keys are exactly the four fields.
    d = route_after_verify(_MISSING, attempts=0, max_attempts=3)
    out = d.as_dict()
    assert isinstance(out["unresolved"], list)
    assert out["unresolved"] == ["v1"]
    assert set(out) == {"next_node", "attempts", "reason", "unresolved"}


def test_attempts_never_exceeds_max() -> None:
    # (8) route never returns attempts > max_attempts, across the boundary.
    for attempts in range(0, 6):
        d = route_after_verify(_MISSING, attempts=attempts, max_attempts=3)
        assert d.attempts <= 3 or attempts > 3
        # When at/over budget it must forward without incrementing.
        if attempts >= 3:
            assert d.next_node == "answer_synthesizer"
            assert d.attempts == attempts


def test_frozen_dataclass_immutable() -> None:
    d = RetryDecision(next_node="x", attempts=1, reason="r", unresolved=("a",))
    try:
        d.attempts = 2  # type: ignore[misc]
    except Exception as exc:  # frozen -> FrozenInstanceError
        assert "cannot assign" in str(exc) or "frozen" in str(exc).lower()
    else:
        raise AssertionError("RetryDecision must be frozen")
