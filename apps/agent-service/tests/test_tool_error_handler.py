"""Hand-checked tests for §13.16 tool-error handler.

Pure-python, no store / no LLM: raise plain exceptions, feed them to
:func:`handle_tool_error`, and assert the exact classified ``kind``, the ``retryable``
flag, the redacted-safe ``message`` and the ``as_dict`` shape. ``should_retry`` is
checked against an attempt budget. Every expected value is spelled out so the test is
verifiable by hand.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from agent_service.tool_error_handler import (
    ToolErrorResult,
    handle_tool_error,
    should_retry,
)


# ---------------------------------------------------------------------------
# handle_tool_error: classification + retryable flag
# ---------------------------------------------------------------------------
def test_timeout_is_retryable() -> None:
    r = handle_tool_error("graph_search", TimeoutError("request timed out"))
    assert r.kind == "timeout"
    assert r.retryable is True
    assert r.tool == "graph_search"


def test_not_found_is_not_retryable() -> None:
    r = handle_tool_error("get_node", KeyError("node not found"))
    # KeyError text matches a not-found hint before the invalid-args hint.
    assert r.kind == "not_found"
    assert r.retryable is False


def test_invalid_args_kind_classified() -> None:
    r = handle_tool_error("numeric_filter", ValueError("invalid comparator"))
    assert r.kind == "invalid_args"
    assert r.retryable is False


def test_unknown_kind_when_unclassifiable() -> None:
    r = handle_tool_error("weird_tool", RuntimeError("kaboom happened"))
    assert r.kind == "unknown"
    assert r.retryable is False


def test_message_redacted_safe() -> None:
    # A secret in the exception text must not survive into the surfaced message.
    exc = RuntimeError("failed with api_key=SUPERSECRETVALUE1234567890abcXYZ boom")
    r = handle_tool_error("t", exc)
    assert "SUPERSECRETVALUE" not in r.message
    assert "SUPERSECRETVALUE1234567890abcXYZ" not in r.message
    assert "[redacted]" in r.message


def test_message_redacts_absolute_path() -> None:
    r = handle_tool_error("t", RuntimeError("cannot open /etc/secrets/db.pem now"))
    assert "/etc/secrets/db.pem" not in r.message
    assert "[redacted]" in r.message


def test_message_falls_back_to_type_name_when_blank() -> None:
    # An exception with an empty message still yields a non-empty reason.
    r = handle_tool_error("t", RuntimeError())
    assert r.message == "RuntimeError"


def test_message_capped_in_length() -> None:
    # Many short words (each < 32 chars, no path) survive redaction but overflow the cap.
    r = handle_tool_error("t", RuntimeError("boom " * 200))
    assert len(r.message) <= 201  # 200 chars + ellipsis
    assert r.message.endswith("…")


# ---------------------------------------------------------------------------
# as_dict: serialisation shape
# ---------------------------------------------------------------------------
def test_as_dict_exact_shape() -> None:
    r = handle_tool_error("graph_search", TimeoutError("timed out"))
    assert r.as_dict() == {
        "tool": "graph_search",
        "kind": "timeout",
        "message": "timed out",
        "retryable": True,
    }


def test_as_dict_from_direct_construction() -> None:
    r = ToolErrorResult(tool="t", kind="not_found", message="нет узла / no node", retryable=False)
    assert r.as_dict() == {
        "tool": "t",
        "kind": "not_found",
        "message": "нет узла / no node",
        "retryable": False,
    }


# ---------------------------------------------------------------------------
# should_retry: retryable flag + attempt budget
# ---------------------------------------------------------------------------
def test_should_retry_true_when_budget_left() -> None:
    r = handle_tool_error("t", TimeoutError("slow"))
    assert should_retry(r, attempt=1, max_attempts=3) is True


def test_should_retry_false_at_max_attempts() -> None:
    r = handle_tool_error("t", TimeoutError("slow"))
    # attempt 3 of 3 already failed → no budget for another try.
    assert should_retry(r, attempt=3, max_attempts=3) is False


def test_should_retry_false_for_non_retryable_kind() -> None:
    r = handle_tool_error("t", ValueError("invalid"))
    assert should_retry(r, attempt=1, max_attempts=5) is False


def test_should_retry_false_when_max_attempts_non_positive() -> None:
    r = handle_tool_error("t", TimeoutError("slow"))
    assert should_retry(r, attempt=1, max_attempts=0) is False


# ---------------------------------------------------------------------------
# frozen: verdicts are immutable
# ---------------------------------------------------------------------------
def test_frozen_is_immutable() -> None:
    r = handle_tool_error("t", TimeoutError("slow"))
    with pytest.raises(FrozenInstanceError):
        r.retryable = False  # type: ignore[misc]
