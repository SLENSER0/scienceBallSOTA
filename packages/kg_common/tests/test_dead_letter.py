"""Tests for dead-letter classification + records (§9.7)."""

from __future__ import annotations

from kg_common.dead_letter import (
    FATAL,
    FATAL_TYPES,
    TRANSIENT,
    TRANSIENT_TYPES,
    UNKNOWN,
    DeadLetterRecord,
    classify_error,
    should_retry,
    to_dead_letter,
)


def test_classify_transient_types() -> None:
    assert classify_error("timeout") == TRANSIENT
    assert classify_error("connection_reset") == TRANSIENT
    assert classify_error("timeout") == "transient"


def test_classify_fatal_types() -> None:
    assert classify_error("schema_validation") == FATAL
    assert classify_error("schema_validation") == "fatal"


def test_classify_unknown() -> None:
    assert classify_error("mystery") == UNKNOWN
    assert classify_error("mystery") == "unknown"


def test_classification_tables_disjoint() -> None:
    # A type cannot be both transient and fatal — таблицы не пересекаются.
    assert TRANSIENT_TYPES.isdisjoint(FATAL_TYPES)


def test_should_retry_transient_within_budget() -> None:
    assert should_retry("timeout", 1, 3) is True
    assert should_retry("timeout", 2, 3) is True


def test_should_retry_transient_budget_exhausted() -> None:
    assert should_retry("timeout", 3, 3) is False
    assert should_retry("timeout", 4, 3) is False


def test_should_retry_fatal_never() -> None:
    assert should_retry("schema_validation", 1, 3) is False


def test_should_retry_unknown_never() -> None:
    assert should_retry("mystery", 1, 3) is False


def test_to_dead_letter_fatal_is_terminal() -> None:
    rec = to_dead_letter("doc:1", "extract", "schema_validation", "bad", 1)
    assert rec.terminal is True


def test_to_dead_letter_unknown_is_terminal() -> None:
    rec = to_dead_letter("doc:2", "extract", "mystery", "huh", 1)
    assert rec.terminal is True


def test_to_dead_letter_transient_within_budget_not_terminal() -> None:
    rec = to_dead_letter("doc:3", "parse", "timeout", "t", 1)
    assert rec.terminal is False


def test_to_dead_letter_transient_budget_exhausted_is_terminal() -> None:
    rec = to_dead_letter("doc:4", "parse", "timeout", "t", 3)
    assert rec.terminal is True


def test_to_dead_letter_transient_custom_max() -> None:
    rec = to_dead_letter("doc:5", "load", "connection_reset", "x", 4, max_attempts=5)
    assert rec.terminal is False


def test_to_dead_letter_as_dict_roundtrip() -> None:
    rec = to_dead_letter("doc:1", "parse", "timeout", "t", 1)
    d = rec.as_dict()
    assert d["error_type"] == "timeout"
    assert d == {
        "doc_id": "doc:1",
        "stage": "parse",
        "error_type": "timeout",
        "message": "t",
        "attempts": 1,
        "terminal": False,
    }


def test_record_is_frozen() -> None:
    rec = DeadLetterRecord("d", "s", "timeout", "m", 1, False)
    try:
        rec.attempts = 9  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("DeadLetterRecord should be immutable")
