"""Tests for §13.22 SSE ChatStreamEvent sequence builder.

Hand-checkable, store-free assertions on :func:`build_stream_sequence`: ordering of
tool_start/tool_end pairs, the closed :data:`EVENT_TYPES` vocabulary, the terminal
``done`` frame, gap/error fan-out, the ``graph`` iff visualization_payload rule, the
failed-trace ``status == 'error'`` marker, and the :meth:`StreamEvent.as_dict` shape.
"""

from __future__ import annotations

from agent_service.stream_events import (
    EVENT_TYPES,
    StreamEvent,
    build_stream_sequence,
)


def _types(events: list[StreamEvent]) -> list[str]:
    return [e.type for e in events]


def test_two_trace_entries_yield_start_end_start_end_order() -> None:
    """Assertion (1): two tool_trace entries -> 4 events in start,end,start,end order."""
    state = {"tool_trace": [{"tool": "graph_search"}, {"tool": "vector_search"}]}
    events = build_stream_sequence(state)
    tool_events = [e for e in events if e.type in {"tool_start", "tool_end"}]
    assert _types(tool_events) == ["tool_start", "tool_end", "tool_start", "tool_end"]
    # names line up with the trace order
    assert [e.data["tool"] for e in tool_events] == [
        "graph_search",
        "graph_search",
        "vector_search",
        "vector_search",
    ]


def test_every_event_type_is_in_event_types() -> None:
    """Assertion (2): every emitted event.type is a member of EVENT_TYPES."""
    state = {
        "tool_trace": [{"tool": "a", "ok": True}, {"tool": "b", "ok": False}],
        "evidence": [{"id": 1}],
        "visualization_payload": {"nodes": []},
        "retrieved_experiments": [{"id": 7}],
        "gaps": ["g1", "g2"],
        "errors": ["boom"],
    }
    events = build_stream_sequence(state)
    assert all(e.type in EVENT_TYPES for e in events)


def test_last_event_is_always_done() -> None:
    """Assertion (3): the terminal event is always type 'done'."""
    assert build_stream_sequence({})[-1].type == "done"
    rich = {"tool_trace": [{"tool": "x"}], "gaps": ["g"], "errors": ["e"]}
    assert build_stream_sequence(rich)[-1].type == "done"


def test_empty_state_yields_exactly_done() -> None:
    """Assertion (4): an empty state maps to exactly [done]."""
    assert _types(build_stream_sequence({})) == ["done"]


def test_two_gaps_yield_two_gap_events() -> None:
    """Assertion (5): two gaps -> two 'gap' events (carrying their payloads)."""
    events = build_stream_sequence({"gaps": ["missing A", "missing B"]})
    gap_events = [e for e in events if e.type == "gap"]
    assert len(gap_events) == 2
    assert [e.data["gap"] for e in gap_events] == ["missing A", "missing B"]


def test_graph_event_present_iff_visualization_payload_truthy() -> None:
    """Assertion (6): a 'graph' event appears iff visualization_payload is truthy."""
    assert "graph" not in _types(build_stream_sequence({}))
    assert "graph" not in _types(build_stream_sequence({"visualization_payload": {}}))
    assert "graph" not in _types(build_stream_sequence({"visualization_payload": None}))
    present = build_stream_sequence({"visualization_payload": {"nodes": [1]}})
    assert "graph" in _types(present)
    graph_event = next(e for e in present if e.type == "graph")
    assert graph_event.data["payload"] == {"nodes": [1]}


def test_tool_end_for_failed_trace_carries_status_error() -> None:
    """Assertion (7): tool_end for a failed trace entry carries status == 'error'."""
    state = {"tool_trace": [{"tool": "ok_tool", "ok": True}, {"tool": "bad", "ok": False}]}
    events = build_stream_sequence(state)
    ends = [e for e in events if e.type == "tool_end"]
    assert ends[0].data["status"] == "ok"
    assert ends[1].data["status"] == "error"


def test_failed_trace_detected_via_status_and_error_fields() -> None:
    """A trace entry marks failure through status/state/error, not only ok=False."""
    for entry in (
        {"tool": "t", "status": "error"},
        {"tool": "t", "state": "failed"},
        {"tool": "t", "error": "kaboom"},
    ):
        events = build_stream_sequence({"tool_trace": [entry]})
        end = next(e for e in events if e.type == "tool_end")
        assert end.data["status"] == "error"


def test_as_dict_shape() -> None:
    """Assertion (8): as_dict() produces exactly {'type', 'data'}."""
    ev = StreamEvent("token", {"text": "hi"})
    d = ev.as_dict()
    assert set(d) == {"type", "data"}
    assert d == {"type": "token", "data": {"text": "hi"}}


def test_full_ordering_of_sections() -> None:
    """The section order is deterministic: tools, evidence, graph, table, gaps, errors, done."""
    state = {
        "tool_trace": [{"tool": "a"}],
        "evidence": [{"id": 1}],
        "visualization_payload": {"nodes": [1]},
        "retrieved_experiments": [{"id": 2}],
        "gaps": ["g"],
        "errors": ["e"],
    }
    assert _types(build_stream_sequence(state)) == [
        "tool_start",
        "tool_end",
        "evidence",
        "graph",
        "table",
        "gap",
        "error",
        "done",
    ]


def test_empty_collections_contribute_no_events() -> None:
    """Empty evidence/experiments/gaps/errors add nothing before the terminal done."""
    state = {
        "tool_trace": [],
        "evidence": [],
        "visualization_payload": {},
        "retrieved_experiments": [],
        "gaps": [],
        "errors": [],
    }
    assert _types(build_stream_sequence(state)) == ["done"]
