"""§13.23 tests — tool-call tracing / traced_tool.

Hand-checkable, deterministic: clocks are lists of pre-baked timestamps, so every
``duration_ms`` is arithmetic we can verify by eye (нет реального времени / no
wall-clock). Covers timing, ok/error status, no-re-raise, camelCase ``dataRef``,
immutable append and ordering.
"""

from __future__ import annotations

from typing import Any

from agent_service.tool_trace import ToolTraceEntry, append_trace, traced_tool


def _fixed_clock(values: list[float]):
    """Clock returning ``values`` in order on each call (детерминированные метки)."""
    it = iter(values)

    def clock() -> float:
        return next(it)

    return clock


def test_duration_ms_from_clock_ticks() -> None:
    """(1) clock 10.0 -> 10.05 yields duration_ms == 50 (round((0.05)*1000))."""
    _, entry = traced_tool("search", lambda a: "hit", {"q": "x"}, _fixed_clock([10.0, 10.05]))
    assert entry.duration_ms == 50


def test_success_status_and_return_value() -> None:
    """(2) a successful run -> status 'ok' and returns fn's value."""
    result, entry = traced_tool("echo", lambda a: a["v"] * 2, {"v": 21}, _fixed_clock([1.0, 1.0]))
    assert result == 42
    assert entry.status == "ok"
    assert entry.error is None


def test_error_status_no_reraise() -> None:
    """(3) raising fn -> status 'error', error has message, result None, no propagation."""

    def boom(_args: dict[str, Any]) -> Any:
        raise RuntimeError("kaboom / бум")

    result, entry = traced_tool("boom", boom, {}, _fixed_clock([2.0, 2.5]))
    assert result is None
    assert entry.status == "error"
    assert "kaboom" in entry.error
    # duration still stamped from the clock across the failing call.
    assert entry.duration_ms == 500


def test_as_dict_uses_camelcase_data_ref() -> None:
    """(4) as_dict() carries camelCase key 'dataRef', not 'data_ref'."""
    entry = ToolTraceEntry(
        tool="t",
        args={"a": 1},
        started_at=0.0,
        finished_at=0.1,
        status="ok",
        summary="s",
        data_ref="doc:42",
    )
    d = entry.as_dict()
    assert d["dataRef"] == "doc:42"
    assert "data_ref" not in d
    assert d["duration_ms"] == 100


def test_append_trace_is_immutable() -> None:
    """(5) append_trace does not mutate input; output length == input + 1."""
    trace: list[dict[str, Any]] = []
    _, entry = traced_tool("t", lambda a: 1, {}, _fixed_clock([0.0, 0.0]))
    out = append_trace(trace, entry)
    assert len(trace) == 0
    assert len(out) == 1
    assert out[0]["tool"] == "t"


def test_two_calls_append_ordered_entries() -> None:
    """(6) two traced calls append two entries in order."""
    trace: list[dict[str, Any]] = []
    _, e1 = traced_tool("first", lambda a: 1, {}, _fixed_clock([0.0, 0.0]))
    _, e2 = traced_tool("second", lambda a: 2, {}, _fixed_clock([0.0, 0.0]))
    trace = append_trace(trace, e1)
    trace = append_trace(trace, e2)
    assert [e["tool"] for e in trace] == ["first", "second"]


def test_duration_ms_non_negative_int() -> None:
    """(7) duration_ms is a non-negative int for equal start/finish stamps."""
    _, entry = traced_tool("t", lambda a: 1, {}, _fixed_clock([5.0, 5.0]))
    assert isinstance(entry.duration_ms, int)
    assert entry.duration_ms >= 0
    assert entry.duration_ms == 0
