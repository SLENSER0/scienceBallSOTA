"""Tests for audit-log formatting + redaction (§19.11)."""

from __future__ import annotations

from datetime import datetime

from kg_common.audit_formatter import audit_line, format_audit_entry

_AT = "2026-07-03T00:00:00Z"


def test_entry_has_core_fields() -> None:
    entry = format_audit_entry("delete", "alice", "node:42", at=_AT)
    assert entry == {
        "action": "delete",
        "actor": "alice",
        "target": "node:42",
        "at": _AT,
    }
    # Without a detail payload the record is exactly the four core keys.
    assert set(entry) == {"action", "actor", "target", "at"}


def test_secret_in_detail_key_redacted() -> None:
    entry = format_audit_entry(
        "login",
        "bob",
        "system",
        detail={"user": "bob", "password": "hunter2"},
        at=_AT,
    )
    assert entry["detail"] == {"user": "bob", "password": "***"}


def test_free_text_secret_in_detail_redacted() -> None:
    # An sk- key embedded in a free-text detail value is masked to its last four.
    key = "sk-abcdefghij0123456789abcdefghij0123456789"
    entry = format_audit_entry(
        "rotate",
        "svc",
        "api",
        detail={"note": f"old key {key}"},
        at=_AT,
    )
    assert entry["detail"] == {"note": "old key sk-***6789"}
    assert key not in entry["detail"]["note"]


def test_audit_line_renders_with_detail() -> None:
    entry = format_audit_entry(
        "delete",
        "alice",
        "node:42",
        detail={"reason": "cleanup", "count": 3},
        at=_AT,
    )
    # Detail keys are rendered sorted: count before reason.
    assert audit_line(entry) == "2026-07-03T00:00:00Z alice delete node:42 count=3 reason=cleanup"


def test_audit_line_without_detail() -> None:
    entry = format_audit_entry("read", "carol", "doc:7", at=_AT)
    assert audit_line(entry) == "2026-07-03T00:00:00Z carol read doc:7"


def test_detail_optional() -> None:
    entry = format_audit_entry("read", "carol", "doc:7", at=_AT)
    assert "detail" not in entry


def test_timestamp_explicit_datetime_isoformat() -> None:
    # A datetime is serialized via isoformat; no wall-clock is ever read.
    at = datetime(2026, 7, 3, 12, 30, 45)
    entry = format_audit_entry("delete", "alice", "node:42", at=at)
    assert entry["at"] == "2026-07-03T12:30:45"


def test_timestamp_explicit_string_passthrough() -> None:
    entry = format_audit_entry("delete", "alice", "node:42", at=_AT)
    assert entry["at"] == _AT


def test_redaction_applied_in_rendered_line() -> None:
    # Redaction happens before rendering, so the secret never reaches the line.
    entry = format_audit_entry(
        "auth",
        "svc",
        "api",
        detail={"token": "supersecrettoken"},
        at=_AT,
    )
    line = audit_line(entry)
    assert "supersecrettoken" not in line
    assert line == "2026-07-03T00:00:00Z svc auth api token=***"


def test_input_detail_not_mutated() -> None:
    detail = {"password": "hunter2", "user": "bob"}
    format_audit_entry("login", "bob", "system", detail=detail, at=_AT)
    # The caller's dict is left untouched — redaction returns a fresh structure.
    assert detail == {"password": "hunter2", "user": "bob"}


def test_deterministic() -> None:
    kwargs = {
        "detail": {"reason": "cleanup", "token": "supersecrettoken"},
        "at": _AT,
    }
    first = format_audit_entry("delete", "alice", "node:42", **kwargs)
    second = format_audit_entry("delete", "alice", "node:42", **kwargs)
    assert first == second
    assert audit_line(first) == audit_line(second)
