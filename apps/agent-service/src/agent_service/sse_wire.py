"""§13.22 SSE wire framing / кадрирование потока событий чата на уровне провода.

:mod:`stream_events` already builds the *ordered* list of :class:`StreamEvent`
objects (§13.22), but nothing turns them into the raw ``text/event-stream`` bytes the
browser's ``EventSource`` reads, nor adds the heartbeat / keep-alive frames the same
section requires on an idle connection. Этот модуль делает ровно это — This module does
exactly that, **purely and deterministically**: no clock, no network, no store, so the
whole wire contract is hand-checkable in a unit test (same events in, same frames out).

Один кадр / one frame is a frozen :class:`SseFrame` carrying up to four SSE fields
(``event`` / ``data`` / ``id`` / ``comment``); :meth:`SseFrame.render` serialises it to
wire text. :func:`encode_frame` builds a data frame (``id`` + ``event`` + compact-JSON
``data``), :func:`heartbeat_frame` builds the ``: keep-alive`` comment frame, and
:func:`encode_stream` maps a ``build_stream_sequence`` output (``{type, data}`` dicts)
to a list of wire strings, splicing in a heartbeat after every ``heartbeat_every``
events when that count is positive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import orjson

__all__ = [
    "SseFrame",
    "encode_frame",
    "encode_stream",
    "heartbeat_frame",
]


def _compact_json(data: dict[str, Any]) -> str:
    """Serialise ``data`` to a single-line JSON string (компактный JSON / no whitespace).

    :func:`orjson.dumps` emits the most compact form and escapes every control
    character — a raw ``\\n`` inside a value becomes the two-byte escape ``\\\\n`` — so
    the returned text is guaranteed free of embedded newlines and safe for one SSE
    ``data:`` line (assertion 4).
    """
    return orjson.dumps(data).decode("utf-8")


@dataclass(frozen=True)
class SseFrame:
    """One Server-Sent-Events frame (§13.22): up to four fields, rendered to wire text.

    Frozen and side-effect-free. A data frame sets ``event``/``data``/``id``; a keep-alive
    frame sets only ``comment``. Field order on the wire is fixed — comment, id, event,
    data — and the frame always terminates with the mandatory blank line (``\\n\\n``).
    """

    event: str | None = None
    data: str | None = None
    id: str | None = None
    comment: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Serialise to a stable four-key dict (``event``/``data``/``id``/``comment``)."""
        return {
            "event": self.event,
            "data": self.data,
            "id": self.id,
            "comment": self.comment,
        }

    def render(self) -> str:
        """Render to ``text/event-stream`` wire text ending in the blank-line ``\\n\\n``."""
        lines: list[str] = []
        if self.comment is not None:
            lines.append(f": {self.comment}")
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.event is not None:
            lines.append(f"event: {self.event}")
        if self.data is not None:
            lines.append(f"data: {self.data}")
        return "\n".join(lines) + "\n\n"


def encode_frame(event_type: str, data: dict[str, Any], seq: int) -> str:
    """Encode one data event to SSE wire text (кадр данных / a single ``event:`` frame).

    Produces ``id: {seq}\\nevent: {event_type}\\ndata: {compact-json}\\n\\n`` where the
    JSON is single-line (see :func:`_compact_json`), so the ``data:`` line never carries a
    raw newline. The ``id:`` line echoes ``seq`` for browser resume / de-duplication.
    """
    return SseFrame(
        event=event_type,
        data=_compact_json(data),
        id=str(seq),
    ).render()


def heartbeat_frame() -> str:
    """Return the keep-alive comment frame ``: keep-alive\\n\\n`` (сердцебиение / heartbeat).

    A comment-only frame (starts with ``:``) that any conforming SSE client silently
    ignores; it exists purely to keep an idle connection and its proxies warm.
    """
    return SseFrame(comment="keep-alive").render()


def encode_stream(events: list[dict[str, Any]], heartbeat_every: int = 0) -> list[str]:
    """Map a stream sequence to wire frames, splicing heartbeats (§13.22).

    Each ``events`` item is a ``{"type": ..., "data": ...}`` dict (as emitted by
    :func:`stream_events.build_stream_sequence` via ``StreamEvent.as_dict``). Every event
    becomes one :func:`encode_frame` string whose ``id:`` is a 0-based counter incrementing
    across the whole stream. When ``heartbeat_every > 0`` a :func:`heartbeat_frame` is
    spliced in after every ``heartbeat_every`` events (heartbeats carry no ``id``).
    """
    frames: list[str] = []
    for seq, event in enumerate(events):
        frames.append(encode_frame(str(event["type"]), event["data"], seq))
        if heartbeat_every > 0 and (seq + 1) % heartbeat_every == 0:
            frames.append(heartbeat_frame())
    return frames
