"""Tests for §13.22 SSE wire framing (:mod:`agent_service.sse_wire`).

Hand-checkable, clock-free, network-free assertions on the wire serialisation:
frame termination (``\\n\\n``), the exact ``event:``/``id:`` lines, JSON-escaping of
embedded newlines, the ``: keep-alive`` heartbeat shape, and heartbeat splicing /
``id`` incrementing across :func:`encode_stream`.
"""

from __future__ import annotations

from agent_service.sse_wire import (
    SseFrame,
    encode_frame,
    encode_stream,
    heartbeat_frame,
)


def _event_line(frame: str) -> str | None:
    for line in frame.split("\n"):
        if line.startswith("event: "):
            return line
    return None


def test_frame_ends_with_blank_line() -> None:
    """Assertion (1): every non-heartbeat frame ends with the mandatory ``\\n\\n``."""
    frames = encode_stream(
        [{"type": "tool_start", "data": {"tool": "x"}}, {"type": "done", "data": {}}],
        heartbeat_every=0,
    )
    for frame in frames:
        assert frame.endswith("\n\n")


def test_event_line_is_exact() -> None:
    """Assertion (2): encode_frame carries a line exactly ``event: tool_start``."""
    frame = encode_frame("tool_start", {"tool": "graph_search"}, 0)
    lines = frame.split("\n")
    assert "event: tool_start" in lines


def test_id_line_equals_seq_and_increments() -> None:
    """Assertion (3): the ``id:`` line equals the passed seq and increments in a stream."""
    assert "id: 7" in encode_frame("token", {}, 7).split("\n")

    events = [{"type": "token", "data": {}} for _ in range(3)]
    frames = encode_stream(events, heartbeat_every=0)
    ids = [next(line for line in f.split("\n") if line.startswith("id: ")) for f in frames]
    assert ids == ["id: 0", "id: 1", "id: 2"]


def test_data_line_has_no_raw_newline() -> None:
    """Assertion (4): a newline inside a value is JSON-escaped, never a raw ``\\n``."""
    frame = encode_frame("error", {"msg": "line1\nline2"}, 0)
    data_lines = [line for line in frame.split("\n") if line.startswith("data: ")]
    assert len(data_lines) == 1  # the value's newline did not split the data field
    assert "\\n" in data_lines[0]  # it is present as the escape sequence
    assert "line1\nline2" not in frame  # ...and never as a raw newline


def test_heartbeat_shape() -> None:
    """Assertion (5): heartbeat_frame starts with ``:`` and has no ``event:`` line."""
    hb = heartbeat_frame()
    assert hb.startswith(":")
    assert hb == ": keep-alive\n\n"
    assert _event_line(hb) is None


def test_lone_done_event_yields_single_done_frame() -> None:
    """Assertion (6): a lone done event -> exactly one frame whose event is ``done``."""
    frames = encode_stream([{"type": "done", "data": {}}], heartbeat_every=0)
    assert len(frames) == 1
    assert _event_line(frames[0]) == "event: done"


def test_heartbeat_splicing_positions() -> None:
    """Assertion (7): 4 events, heartbeat_every=2 -> 6 strings, heartbeats at idx 2 and 5."""
    events = [{"type": "token", "data": {"i": i}} for i in range(4)]
    frames = encode_stream(events, heartbeat_every=2)
    assert len(frames) == 6
    heartbeat_idx = [i for i, f in enumerate(frames) if f == heartbeat_frame()]
    assert heartbeat_idx == [2, 5]
    # the surviving event frames keep a contiguous 0..3 id run
    event_ids = [
        next(line for line in f.split("\n") if line.startswith("id: "))
        for f in frames
        if _event_line(f) is not None
    ]
    assert event_ids == ["id: 0", "id: 1", "id: 2", "id: 3"]


def test_last_frame_event_is_done() -> None:
    """Assertion (8): the last emitted frame's event line is ``done``."""
    events = [
        {"type": "tool_start", "data": {"tool": "a"}},
        {"type": "tool_end", "data": {"tool": "a", "status": "ok"}},
        {"type": "evidence", "data": {"count": 2}},
        {"type": "done", "data": {}},
    ]
    frames = encode_stream(events, heartbeat_every=0)
    assert _event_line(frames[-1]) == "event: done"


def test_sseframe_as_dict_shape() -> None:
    """SseFrame.as_dict exposes the stable four-key shape; render round-trips fields."""
    frame = SseFrame(event="done", data="{}", id="3")
    assert frame.as_dict() == {"event": "done", "data": "{}", "id": "3", "comment": None}
    assert frame.render() == "id: 3\nevent: done\ndata: {}\n\n"
