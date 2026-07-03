"""§13.22 стриминг — противодавление буфера SSE / streaming — SSE backpressure buffer.

:mod:`sse_wire` owns the wire framing and :mod:`token_stream` owns the delta→text
accumulation; this module owns the third half of the §13.22 producer contract — the
*backpressure* / keep-alive buffer that sits between the LLM producing events and the
слушатель / consumer draining them. When the consumer is slower than the producer the
buffer must stay bounded (ограниченный буфер) without ever losing the answer's shape:

* consecutive ``token`` events **coalesce** (склеиваются) — their ``text`` fields are
  concatenated into a single buffered token event, so a burst of tiny deltas collapses;
* any non-``token`` event (e.g. a ``graph`` frame) **breaks** the coalescing run, so
  structure between two token bursts is preserved as separate entries;
* terminal events (``error`` / ``end``) are **never dropped** — the stream's ending is
  sacred even when the buffer is already at capacity (буфер переполнен → всё равно храним);
* when a non-terminal event would overflow ``max_size`` the **oldest non-terminal** entry
  is dropped and :attr:`BackpressureBuffer.dropped` is incremented (счётчик потерь).

Everything here is pure and deterministic: no clock, no network, no store, so the whole
backpressure contract is hand-checkable in a unit test (same pushes in, same buffer out).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

__all__ = [
    "BackpressureBuffer",
    "flush",
    "push",
]

# Event type that coalesces (склеивается) and its concatenated field.
_TOKEN_EVENT = "token"
_TEXT_FIELD = "text"

# Terminal event types (never dropped / никогда не отбрасываются).
_TERMINAL_TYPES = frozenset({"error", "end"})


def _event_type(event: dict[str, Any]) -> Any:
    """Return the event's ``type`` tag (тип события), or ``None`` when absent."""
    return event.get("type")


def _is_terminal(event: dict[str, Any]) -> bool:
    """Whether ``event`` is a terminal ``error`` / ``end`` frame (терминальное событие)."""
    return _event_type(event) in _TERMINAL_TYPES


@dataclass(frozen=True)
class BackpressureBuffer:
    """Immutable bounded buffer for the SSE producer (§13.22 backpressure).

    ``events`` is the ordered tuple of buffered event dicts (буферизованные события);
    ``max_size`` is the soft cap on non-terminal entries (мягкий предел); ``dropped`` counts
    how many non-terminal events were shed to honour that cap (число отброшенных). Terminal
    frames may push the length past ``max_size`` — the ending is never sacrificed.
    """

    events: tuple[dict[str, Any], ...] = ()
    max_size: int = 64
    dropped: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{events, max_size, dropped}`` (для транспорта / for the wire)."""
        return {
            "events": [dict(event) for event in self.events],
            "max_size": self.max_size,
            "dropped": self.dropped,
        }


def _coalesce_last(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    """Merge ``event``'s ``text`` into the trailing token entry in place (склейка дельт).

    A NEW dict replaces the tail so the input buffer's own dict is never mutated
    (immutability / неизменяемость сохраняется); все прочие поля наследуются от хвоста.
    """
    last = events[-1]
    merged = {**last, _TEXT_FIELD: last.get(_TEXT_FIELD, "") + event.get(_TEXT_FIELD, "")}
    events[-1] = merged


def _drop_oldest_non_terminal(events: list[dict[str, Any]]) -> bool:
    """Drop the oldest non-terminal entry in place; return whether one was dropped.

    Terminal frames are skipped (терминальные не трогаем); when the buffer holds only
    terminal events nothing is dropped and ``False`` is returned.
    """
    for index, buffered in enumerate(events):
        if not _is_terminal(buffered):
            del events[index]
            return True
    return False


def push(buf: BackpressureBuffer, event: dict[str, Any]) -> BackpressureBuffer:
    """Fold ``event`` into a NEW buffer, coalescing / bounding per §13.22 (immutable).

    Rules, in order: a ``token`` event whose предшественник is also a buffered ``token``
    coalesces (текст склеивается) and never grows the buffer; any other event starts a new
    entry. Before appending a **non-terminal** entry to a full buffer (``len >= max_size``)
    the oldest non-terminal event is dropped and ``dropped`` is bumped. Terminal ``error`` /
    ``end`` events are always appended — even past ``max_size`` — and never trigger a drop.
    The input ``buf`` is never mutated (frozen dataclass → fresh instance every call).
    """
    events = list(buf.events)

    # Coalescing run: consecutive token events merge их text без роста буфера.
    if _event_type(event) == _TOKEN_EVENT and events and _event_type(events[-1]) == _TOKEN_EVENT:
        _coalesce_last(events, event)
        return replace(buf, events=tuple(events))

    dropped = buf.dropped
    overflowing = not _is_terminal(event) and len(events) >= buf.max_size
    if overflowing and _drop_oldest_non_terminal(events):
        dropped += 1

    events.append(dict(event))
    return replace(buf, events=tuple(events), dropped=dropped)


def flush(buf: BackpressureBuffer) -> list[dict[str, Any]]:
    """Return a shallow list copy of the buffered events (слить буфер / drain to a list).

    The returned list is a fresh container the caller may consume freely; ``buf`` itself is
    left untouched (frozen dataclass), so flushing never disturbs the producer's state.
    """
    return [dict(event) for event in buf.events]
