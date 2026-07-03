"""Tests for the §12.10 Text2Cypher retry/verifier decision logic.

Hand-checkable coverage of :func:`classify_error` keyword rules and the
:func:`decide` state machine (retry -> fallback_template -> give_up).
"""

from __future__ import annotations

from kg_retrievers.text2cypher_retry import (
    ACTION_FALLBACK,
    ACTION_GIVE_UP,
    ACTION_RETRY,
    RetryDecision,
    classify_error,
    decide,
)

# --- classify_error keyword rules ----------------------------------------


def test_classify_syntax_error_word() -> None:
    assert classify_error("SyntaxError near WHERE") == "syntax"


def test_classify_invalid_input() -> None:
    assert classify_error("Invalid input '(' expected identifier") == "syntax"


def test_classify_empty_zero_rows() -> None:
    assert classify_error("query returned 0 rows") == "empty_result"


def test_classify_empty_no_rows() -> None:
    assert classify_error("no rows matched the pattern") == "empty_result"


def test_classify_empty_bare_word() -> None:
    assert classify_error("result set is empty") == "empty_result"


def test_classify_timeout() -> None:
    assert classify_error("execution timeout after 30s") == "timeout"


def test_classify_timeout_timed_out() -> None:
    assert classify_error("query timed out") == "timeout"


def test_classify_guardrail_disallowed() -> None:
    assert classify_error("disallowed clause DETACH DELETE") == "guardrail"


def test_classify_guardrail_allowlist() -> None:
    assert classify_error("label Foo not in allowlist") == "guardrail"


def test_classify_guardrail_write() -> None:
    assert classify_error("write operations are blocked") == "guardrail"


def test_classify_unknown() -> None:
    assert classify_error("connection reset by peer") == "unknown"


def test_classify_empty_string_is_unknown() -> None:
    assert classify_error("") == "unknown"


def test_classify_case_insensitive() -> None:
    assert classify_error("SYNTAXERROR") == "syntax"


def test_guardrail_beats_incidental_syntax_wording() -> None:
    # Guardrail signal must outrank an incidental 'syntax' word in the message.
    assert classify_error("write blocked despite valid syntax") == "guardrail"


# --- decide: spec assertions ---------------------------------------------


def test_decide_syntax_below_max_retries() -> None:
    assert decide(1, 3, "syntax", template_available=True).action == ACTION_RETRY


def test_decide_syntax_at_max_falls_back() -> None:
    d = decide(3, 3, "syntax", template_available=True)
    assert d.action == ACTION_FALLBACK


def test_decide_guardrail_never_retries_with_template() -> None:
    # attempt < max but guardrail -> fallback, no retry.
    d = decide(1, 3, "guardrail", template_available=True)
    assert d.action == ACTION_FALLBACK


def test_decide_guardrail_no_template_gives_up() -> None:
    d = decide(1, 3, "guardrail", template_available=False)
    assert d.action == ACTION_GIVE_UP


def test_decide_empty_result_retries() -> None:
    assert decide(1, 3, "empty_result", template_available=True).action == ACTION_RETRY


# --- decide: additional edges --------------------------------------------


def test_decide_timeout_retries_below_max() -> None:
    assert decide(2, 3, "timeout", template_available=False).action == ACTION_RETRY


def test_decide_exhausted_no_template_gives_up() -> None:
    d = decide(3, 3, "syntax", template_available=False)
    assert d.action == ACTION_GIVE_UP


def test_decide_beyond_max_falls_back() -> None:
    # attempt > max_attempts is treated the same as == max_attempts.
    d = decide(5, 3, "timeout", template_available=True)
    assert d.action == ACTION_FALLBACK


def test_decide_unknown_kind_retries() -> None:
    assert decide(1, 3, "unknown", template_available=True).action == ACTION_RETRY


def test_decide_guardrail_at_max_still_fallback() -> None:
    # Attempt at max makes no difference for guardrail; still fallback.
    assert decide(3, 3, "guardrail", template_available=True).action == ACTION_FALLBACK


def test_decide_single_attempt_budget_falls_back() -> None:
    # max_attempts == 1: first failure already exhausts the budget.
    assert decide(1, 1, "syntax", template_available=True).action == ACTION_FALLBACK


# --- RetryDecision dataclass ---------------------------------------------


def test_as_dict_shape() -> None:
    d = decide(1, 3, "syntax", template_available=True)
    assert d.as_dict() == {"action": "retry", "attempt": 1, "reason": d.reason}
    assert set(d.as_dict()) == {"action", "attempt", "reason"}


def test_retry_decision_is_frozen() -> None:
    d = RetryDecision(action="retry", attempt=1, reason="x")
    try:
        d.action = "give_up"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("RetryDecision must be frozen")


def test_attempt_preserved_in_decision() -> None:
    assert decide(2, 5, "timeout", template_available=False).attempt == 2
