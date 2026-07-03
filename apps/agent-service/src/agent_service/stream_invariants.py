"""§13.22 Consumer-side invariant validation of a *received* ChatStreamEvent stream.

The producer (``stream_events.py``) only *builds* a correctly ordered SSE sequence
from a completed agent state. But the api-gateway proxies an **arbitrary** upstream
producer to the browser: nothing checks that the frames actually *consumed* on the
other end still satisfy the §13.22 stream contract. This module is that check — a
pure, hand-checkable validator over the wire-shape ``{'type', 'data'}`` dicts.

Инварианты потока / stream invariants enforced by :func:`check_stream`:

1. exactly one terminal ``done`` event, and it is the **last** element;
2. no event follows ``done`` (redundant with (1) but reported separately);
3. every ``tool_end`` is preceded by a matching ``tool_start`` for the same
   ``data['tool']`` (парный вызов / balanced tool span);
4. each event ``type`` is in the known ChatStreamEvent union (:data:`KNOWN_TYPES`);
5. all ``token`` events precede ``done`` (нет токенов после финала / no post-final
   tokens).

The result is a frozen :class:`StreamCheck` — ``ok`` plus the ordered tuple of human
readable ``problems`` (empty iff ``ok``). Serialise with :meth:`StreamCheck.as_dict`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["KNOWN_TYPES", "StreamCheck", "check_stream"]

#: Known ChatStreamEvent union — mirrors ``stream_events.EVENT_TYPES`` (§13.22).
KNOWN_TYPES: tuple[str, ...] = (
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
class StreamCheck:
    """Verdict of :func:`check_stream` (результат проверки / validation verdict).

    ``ok`` is ``True`` iff ``problems`` is empty; ``problems`` is an ordered tuple of
    human-readable invariant violations. Frozen and JSON-serialisable via
    :meth:`as_dict`.
    """

    ok: bool
    problems: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{'ok': bool, 'problems': [...]}`` (``problems`` is a list)."""
        return {"ok": self.ok, "problems": list(self.problems)}


def _event_type(event: dict[str, Any]) -> str:
    """Best-effort ``type`` of a wire event (тип кадра / frame type label)."""
    return str(event.get("type", "")) if isinstance(event, dict) else ""


def _tool_name(event: dict[str, Any]) -> str:
    """Tool name carried by a tool_start/tool_end frame (имя инструмента)."""
    data = event.get("data") if isinstance(event, dict) else None
    if isinstance(data, dict):
        return str(data.get("tool", ""))
    return ""


def check_stream(events: list[dict[str, Any]]) -> StreamCheck:
    """Validate a *consumed* ChatStreamEvent sequence against §13.22 invariants.

    Walks ``events`` (each a ``{'type', 'data'}`` dict) once, collecting every
    violation in encounter order. Returns a :class:`StreamCheck` whose ``ok`` is
    ``True`` iff no problem was found (a well-formed stream yields an empty tuple).
    """
    problems: list[str] = []

    # --- (4) unknown event types / неизвестные типы кадров -----------------------
    for i, event in enumerate(events):
        etype = _event_type(event)
        if etype not in KNOWN_TYPES:
            problems.append(f"event[{i}] has unknown type {etype!r} (not a ChatStreamEvent)")

    # --- (1) exactly one terminal 'done', and it is last -------------------------
    done_indexes = [i for i, e in enumerate(events) if _event_type(e) == "done"]
    if not done_indexes:
        problems.append("missing terminal 'done' event (stream must end with 'done')")
    elif len(done_indexes) > 1:
        problems.append(f"expected exactly one terminal 'done', found {len(done_indexes)}")
    last_done = done_indexes[0] if done_indexes else None
    if done_indexes and done_indexes[0] != len(events) - 1:
        problems.append("'done' is not the last event of the stream")

    # --- (2) no event follows 'done' / после 'done' ничего нет -------------------
    if last_done is not None:
        for i in range(last_done + 1, len(events)):
            problems.append(f"event[{i}] ({_event_type(events[i])!r}) follows terminal 'done'")

    # --- (3) every 'tool_end' has a prior matching 'tool_start' ------------------
    open_tools: dict[str, int] = {}
    for i, event in enumerate(events):
        etype = _event_type(event)
        if etype == "tool_start":
            tool = _tool_name(event)
            open_tools[tool] = open_tools.get(tool, 0) + 1
        elif etype == "tool_end":
            tool = _tool_name(event)
            if open_tools.get(tool, 0) <= 0:
                problems.append(
                    f"event[{i}] 'tool_end' for tool {tool!r} has no prior matching 'tool_start'"
                )
            else:
                open_tools[tool] -= 1

    # --- (5) all 'token' events precede 'done' -----------------------------------
    if last_done is not None:
        for i, event in enumerate(events):
            if _event_type(event) == "token" and i > last_done:
                problems.append(f"event[{i}] 'token' occurs after terminal 'done'")

    return StreamCheck(ok=not problems, problems=tuple(problems))
