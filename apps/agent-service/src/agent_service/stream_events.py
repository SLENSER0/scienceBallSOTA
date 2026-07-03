"""§13.22 SSE ChatStreamEvent sequence builder / построитель потока событий чата.

Turns a *completed* agent state (§13.11) into the ordered list of Server-Sent-Event
frames the chat transport pushes to the browser. The mapping is **pure and
deterministic** — no store, no LLM, no clock — so the whole SSE contract is
hand-checkable in a unit test: same state in, same event sequence out.

Событие потока / one stream frame is a frozen :class:`StreamEvent` carrying a
``type`` (one of :data:`EVENT_TYPES`) and a JSON-serialisable ``data`` dict.
:func:`build_stream_sequence` walks the state in a fixed order:

1. one ``tool_start`` + ``tool_end`` pair per ``state['tool_trace']`` entry, in
   order (a failed entry's ``tool_end`` carries ``status == 'error'``);
2. one ``evidence`` event iff ``state['evidence']`` is non-empty;
3. one ``graph`` event iff ``state['visualization_payload']`` is truthy;
4. one ``table`` event iff ``state['retrieved_experiments']`` is non-empty;
5. one ``gap`` event per ``state['gaps']`` entry;
6. one ``error`` event per ``state['errors']`` entry;
7. always a terminal ``done`` event last (даже для пустого состояния / even for an
   empty state, the sequence is exactly ``[done]``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["EVENT_TYPES", "StreamEvent", "build_stream_sequence"]

#: Allowed values of :attr:`StreamEvent.type` (замкнутый словарь / closed vocabulary).
EVENT_TYPES: tuple[str, ...] = (
    "token",
    "tool_start",
    "tool_end",
    "evidence",
    "graph",
    "table",
    "gap",
    "error",
    "done",
)


@dataclass(frozen=True)
class StreamEvent:
    """One SSE frame (§13.22): a ``type`` from :data:`EVENT_TYPES` plus a ``data`` dict.

    Frozen and JSON-serialisable via :meth:`as_dict`; the builder never mutates an
    event after creation (события неизменяемы / events are immutable).
    """

    type: str
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{'type': type, 'data': data}`` (stable two-key shape)."""
        return {"type": self.type, "data": self.data}


def _trace_failed(entry: Any) -> bool:
    """Did this ``tool_trace`` entry fail? (ошибка вызова / a failed tool call).

    Tolerant of the shapes a trace entry takes: an explicit ``ok=False`` flag, a
    ``status``/``state`` of ``"error"``/``"fail"``, or a truthy ``error`` field all
    count as a failure. Non-mapping entries (e.g. a bare tool name) never fail.
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("ok") is False:
        return True
    if str(entry.get("status", "")).lower() in {"error", "failed", "fail"}:
        return True
    if str(entry.get("state", "")).lower() in {"error", "failed", "fail"}:
        return True
    return bool(entry.get("error"))


def _trace_tool_name(entry: Any) -> str:
    """Best-effort tool name for a trace entry (имя инструмента / tool label)."""
    if isinstance(entry, dict):
        return str(entry.get("tool") or entry.get("name") or "")
    return str(entry)


def build_stream_sequence(state: dict[str, Any]) -> list[StreamEvent]:
    """Map a completed agent ``state`` to its ordered SSE event sequence (§13.22).

    The order is fixed (see the module docstring): tool_start/tool_end pairs, then
    ``evidence``, ``graph``, ``table``, one ``gap`` per gap, one ``error`` per error,
    and always a terminal ``done``. Missing/empty state keys simply contribute no
    events, so an empty state yields exactly ``[done]``.
    """
    events: list[StreamEvent] = []

    for entry in state.get("tool_trace") or ():
        tool = _trace_tool_name(entry)
        failed = _trace_failed(entry)
        events.append(StreamEvent("tool_start", {"tool": tool}))
        events.append(
            StreamEvent(
                "tool_end",
                {"tool": tool, "status": "error" if failed else "ok"},
            )
        )

    if state.get("evidence"):
        events.append(StreamEvent("evidence", {"count": len(state["evidence"])}))

    if state.get("visualization_payload"):
        events.append(StreamEvent("graph", {"payload": state["visualization_payload"]}))

    if state.get("retrieved_experiments"):
        events.append(StreamEvent("table", {"count": len(state["retrieved_experiments"])}))

    for gap in state.get("gaps") or ():
        events.append(StreamEvent("gap", {"gap": gap}))

    for error in state.get("errors") or ():
        events.append(StreamEvent("error", {"error": error}))

    events.append(StreamEvent("done", {}))
    return events
