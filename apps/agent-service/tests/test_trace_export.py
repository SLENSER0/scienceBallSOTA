"""§13.23 тесты экспорта трассировки с редактированием / trace-export redaction tests."""

from __future__ import annotations

import json

import pytest
from agent_service.trace_export import (
    DEFAULT_SENSITIVE,
    TraceExport,
    build_trace_export,
    redact_args,
)


def test_redact_top_level_secret() -> None:
    """(1) api_key redacted, non-sensitive value kept."""
    assert redact_args({"api_key": "x", "q": "Al"}) == {"api_key": "***", "q": "Al"}


def test_redaction_is_case_insensitive() -> None:
    """(2) uppercase key API_KEY is still redacted."""
    assert redact_args({"API_KEY": "secret"}) == {"API_KEY": "***"}


def test_nested_dict_redacted() -> None:
    """(3) sensitive key inside a nested dict is redacted."""
    assert redact_args({"cfg": {"password": "p"}}) == {"cfg": {"password": "***"}}


def test_non_sensitive_untouched() -> None:
    """(4) values without sensitive keys are preserved exactly."""
    src = {"query": "Al-Cu", "top_k": 5, "opts": {"verbose": True}}
    assert redact_args(src) == src


def test_build_counts_two_entries() -> None:
    """(5) two entries → tool_calls == 2."""
    trace = [
        {"tool": "search", "args": {"q": "Al"}},
        {"tool": "fetch", "args": {"api_key": "k"}},
    ]
    export = build_trace_export("sess-1", trace)
    assert export.tool_calls == 2


def test_redacted_keys_lists_present_secret() -> None:
    """(6a) redacted_keys reports the api_key that was scrubbed."""
    trace = [{"tool": "fetch", "args": {"api_key": "k", "q": "Al"}}]
    export = build_trace_export("sess-1", trace)
    assert export.redacted_keys == ("api_key",)
    # inner value actually redacted / значение действительно скрыто
    assert export.entries[0]["args"] == {"api_key": "***", "q": "Al"}


def test_redacted_keys_empty_when_no_secret() -> None:
    """(6b) no sensitive keys → empty redacted_keys tuple."""
    trace = [{"tool": "search", "args": {"q": "Al"}}]
    export = build_trace_export("sess-1", trace)
    assert export.redacted_keys == ()


def test_empty_trace() -> None:
    """(7) empty trace → tool_calls 0 and empty entries."""
    export = build_trace_export("sess-1", [])
    assert export.tool_calls == 0
    assert export.entries == ()


def test_as_dict_json_serialisable() -> None:
    """(8) as_dict round-trips through json.dumps/loads."""
    trace = [{"tool": "fetch", "args": {"password": "p", "q": "Al"}}]
    export = build_trace_export("sess-9", trace)
    payload = json.dumps(export.as_dict())
    loaded = json.loads(payload)
    assert loaded["session_id"] == "sess-9"
    assert loaded["tool_calls"] == 1
    assert loaded["redacted_keys"] == ["password"]
    assert loaded["entries"][0]["args"] == {"password": "***", "q": "Al"}


def test_input_not_mutated() -> None:
    """redact_args / build_trace_export never mutate their inputs."""
    args = {"token": "t", "q": "Al"}
    redact_args(args)
    assert args == {"token": "t", "q": "Al"}
    trace = [{"tool": "fetch", "args": {"token": "t"}}]
    build_trace_export("s", trace)
    assert trace == [{"tool": "fetch", "args": {"token": "t"}}]


def test_list_of_dicts_redacted() -> None:
    """Secrets inside dicts nested in a list are redacted, structure preserved."""
    src = {"items": [{"authorization": "Bearer x"}, {"name": "ok"}]}
    assert redact_args(src) == {"items": [{"authorization": "***"}, {"name": "ok"}]}


def test_custom_sensitive_set() -> None:
    """A caller-supplied sensitive set overrides the default."""
    assert redact_args({"secret": "s", "api_key": "k"}, frozenset({"secret"})) == {
        "secret": "***",
        "api_key": "k",
    }


def test_default_sensitive_membership() -> None:
    """DEFAULT_SENSITIVE holds the documented credential key names."""
    assert {"password", "token", "api_key", "authorization", "llm_api_key"} <= DEFAULT_SENSITIVE


def test_trace_export_frozen() -> None:
    """TraceExport is immutable."""
    export = build_trace_export("s", [])
    assert isinstance(export, TraceExport)
    with pytest.raises((AttributeError, TypeError)):
        export.session_id = "other"  # type: ignore[misc]
