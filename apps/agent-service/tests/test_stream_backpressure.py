"""Tests for §13.22 SSE backpressure buffer / противодавление буфера потока."""

from __future__ import annotations

from agent_service.stream_backpressure import (
    BackpressureBuffer,
    flush,
    push,
)


def _token(text: str) -> dict[str, str]:
    """A ``token`` event carrying ``text`` (событие-токен / streamed delta)."""
    return {"type": "token", "text": text}


def test_two_tokens_coalesce_into_one_entry() -> None:
    """(1) two consecutive token events → single event, concatenated text (Al+Cu)."""
    buf = BackpressureBuffer(max_size=8)
    buf = push(buf, _token("Al"))
    buf = push(buf, _token("Cu"))
    assert len(buf.events) == 1
    assert buf.events[0]["text"] == "AlCu"


def test_graph_between_tokens_breaks_the_run() -> None:
    """(2) a graph event between two tokens yields three buffered entries."""
    buf = BackpressureBuffer(max_size=8)
    buf = push(buf, _token("a"))
    buf = push(buf, {"type": "graph", "data": {"nodes": 2}})
    buf = push(buf, _token("b"))
    assert len(buf.events) == 3
    assert [e["type"] for e in buf.events] == ["token", "graph", "token"]


def test_overflow_drops_oldest_non_terminal_and_counts() -> None:
    """(3) pushing past max_size drops the oldest non-terminal and bumps dropped."""
    buf = BackpressureBuffer(max_size=2)
    buf = push(buf, {"type": "graph", "data": {"i": 0}})
    buf = push(buf, {"type": "graph", "data": {"i": 1}})
    assert len(buf.events) == 2
    assert buf.dropped == 0
    buf = push(buf, {"type": "graph", "data": {"i": 2}})
    assert len(buf.events) == 2  # bounded — length held at the cap
    assert buf.dropped == 1
    # oldest (i==0) shed; newest (i==2) retained.
    assert [e["data"]["i"] for e in buf.events] == [1, 2]


def test_end_event_retained_at_capacity() -> None:
    """(4) a terminal 'end' event is kept even when the buffer is full."""
    buf = BackpressureBuffer(max_size=2)
    buf = push(buf, {"type": "graph", "data": {"i": 0}})
    buf = push(buf, {"type": "graph", "data": {"i": 1}})
    buf = push(buf, {"type": "end"})
    assert len(buf.events) == 3  # terminal frame exceeds max_size on purpose
    assert buf.dropped == 0  # nothing dropped for a terminal event
    assert buf.events[-1] == {"type": "end"}


def test_error_event_also_never_dropped() -> None:
    """(4b) a terminal 'error' event is appended past capacity without a drop."""
    buf = BackpressureBuffer(max_size=1)
    buf = push(buf, {"type": "graph", "data": {"i": 0}})
    buf = push(buf, {"type": "error", "message": "boom"})
    assert len(buf.events) == 2
    assert buf.dropped == 0
    assert buf.events[-1]["type"] == "error"


def test_flush_returns_list_of_same_length() -> None:
    """(5) flush returns a list whose length equals buffer.events."""
    buf = BackpressureBuffer(max_size=8)
    buf = push(buf, _token("x"))
    buf = push(buf, {"type": "graph", "data": {}})
    drained = flush(buf)
    assert isinstance(drained, list)
    assert len(drained) == len(buf.events) == 2


def test_push_leaves_input_buffer_unchanged() -> None:
    """(6) the input buffer object is unchanged after push (immutability)."""
    buf = BackpressureBuffer(max_size=8)
    buf = push(buf, _token("Al"))
    before_events = buf.events
    before_dropped = buf.dropped
    result = push(buf, _token("Cu"))
    # original untouched — coalescing built a NEW dict, not mutated the old one.
    assert buf.events is before_events
    assert buf.events[0]["text"] == "Al"
    assert buf.dropped == before_dropped
    assert result is not buf
    assert result.events[0]["text"] == "AlCu"


def test_fresh_buffer_has_zero_dropped() -> None:
    """(7) a fresh buffer starts with dropped == 0 and no events."""
    buf = BackpressureBuffer()
    assert buf.dropped == 0
    assert buf.events == ()


def test_as_dict_round_trips_fields() -> None:
    """as_dict exposes events/max_size/dropped verbatim (для транспорта)."""
    buf = BackpressureBuffer(max_size=4)
    buf = push(buf, _token("hi"))
    assert buf.as_dict() == {
        "events": [{"type": "token", "text": "hi"}],
        "max_size": 4,
        "dropped": 0,
    }


def test_overflow_by_token_after_break_drops_oldest() -> None:
    """A non-coalescing token at capacity still drops the oldest non-terminal."""
    buf = BackpressureBuffer(max_size=2)
    buf = push(buf, {"type": "graph", "data": {"i": 0}})
    buf = push(buf, {"type": "graph", "data": {"i": 1}})
    # token does not coalesce (tail is a graph event) → treated as a new entry.
    buf = push(buf, _token("z"))
    assert len(buf.events) == 2
    assert buf.dropped == 1
    assert buf.events[-1] == {"type": "token", "text": "z"}
