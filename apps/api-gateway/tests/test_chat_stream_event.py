"""Tests for §14.4 chat SSE / ``ChatStreamEvent`` serialization."""

from __future__ import annotations

import dataclasses
import json

import pytest
from api_gateway.chat_stream_event import (
    EVENT_TYPES,
    ChatStreamEvent,
    heartbeat_frame,
    parse_last_event_id,
    to_sse_frame,
    validate_event,
)


def test_event_types_cover_spec() -> None:
    expected = frozenset(
        {"token", "tool_start", "tool_end", "evidence", "graph", "table", "gap", "error"}
    )
    assert expected == EVENT_TYPES


def test_validate_event_accepts_known_type() -> None:
    ev = validate_event("token", {"text": "hi"})
    assert isinstance(ev, ChatStreamEvent)
    assert ev.type == "token"
    assert ev.data == {"text": "hi"}
    assert ev.event_id is None


def test_validate_event_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        validate_event("bogus", {})


def test_event_is_frozen() -> None:
    ev = validate_event("token", {"t": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.type = "gap"  # type: ignore[misc]


def test_to_sse_frame_shape() -> None:
    frame = to_sse_frame(validate_event("token", {"t": 1}))
    assert b"event: token\n" in frame
    assert b"data: " in frame
    assert frame.endswith(b"\n\n")


def test_to_sse_frame_data_is_json() -> None:
    frame = to_sse_frame(validate_event("gap", {"reason": "нет данных", "n": 2}))
    line = frame.decode().splitlines()[0]
    assert line.startswith("event: gap")
    data_line = next(x for x in frame.decode().splitlines() if x.startswith("data: "))
    assert json.loads(data_line[len("data: ") :]) == {"reason": "нет данных", "n": 2}


def test_frame_with_event_id_prefix() -> None:
    frame = to_sse_frame(validate_event("token", {"t": 1}, event_id="7"))
    assert frame.startswith(b"id: 7\n")
    assert b"event: token\n" in frame


def test_frame_without_event_id_omits_id() -> None:
    frame = to_sse_frame(validate_event("token", {"t": 1}, event_id=None))
    assert b"id:" not in frame


def test_heartbeat_frame_default() -> None:
    assert heartbeat_frame() == b": keep-alive\n\n"


def test_heartbeat_frame_custom_comment() -> None:
    assert heartbeat_frame("ping") == b": ping\n\n"


def test_parse_last_event_id() -> None:
    assert parse_last_event_id("5") == "5"
    assert parse_last_event_id(None) is None
    assert parse_last_event_id("  9  ") == "9"
    assert parse_last_event_id("   ") is None


def test_as_dict_mirrors_event_id() -> None:
    ev = validate_event("token", {"t": 1}, event_id="7")
    assert ev.as_dict() == {"type": "token", "data": {"t": 1}, "id": "7"}
    assert ev.as_dict()["id"] == "7"


def test_as_dict_id_none_when_unset() -> None:
    assert validate_event("token", {"t": 1}).as_dict()["id"] is None
