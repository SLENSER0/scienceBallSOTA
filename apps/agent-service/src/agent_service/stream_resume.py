"""§13.22 SSE Last-Event-ID reconnect replay / повтор хвоста потока после переподключения.

:mod:`sse_wire` stamps every data frame with a monotonic ``id`` field, and §13.22 requires
a reconnecting ``EventSource`` to resume *where it left off* by echoing its last seen id in
the ``Last-Event-ID`` request header. Ничто пока не воспроизводит хвост потока — nothing yet
replays the tail of the stream after that id, so this module supplies the pure, deterministic
resume logic: no store, no network, no clock, so the whole reconnect contract is
hand-checkable in a unit test (same events + same id in, same slice out).

:func:`index_events` stamps a :func:`build_stream_sequence` output (``{type, data}`` dicts)
with a 0-based ``seq``; :func:`resume_after` returns the :class:`ResumeSlice` of every event
whose ``seq`` is strictly greater than the client's ``last_event_id`` (полный повтор / a full
replay when the id is ``None`` or negative), flagging ``is_exhausted`` iff the slice is empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "ResumeSlice",
    "index_events",
    "resume_after",
]


def index_events(events: list[dict]) -> list[dict]:
    """Stamp each event with a strictly increasing 0-based ``seq`` (индексация кадров).

    Returns a new list of shallow-copied dicts so the caller's input is never mutated; every
    original key (``type`` / ``data`` / …) is preserved and a fresh ``seq`` is added. The
    ``n``-th event carries ``seq == n``, matching the ``id`` field :mod:`sse_wire` puts on the
    wire (assertion 6).
    """
    return [{**event, "seq": i} for i, event in enumerate(events)]


@dataclass(frozen=True)
class ResumeSlice:
    """The tail of a stream to replay after a reconnect (§13.22): frozen and serialisable.

    ``from_seq`` — the first ``seq`` a resuming client should expect (``last_event_id + 1``,
    clamped to ``0``); ``events`` — the immutable tuple of indexed events with ``seq`` greater
    than the client's last id; ``is_exhausted`` — ``True`` iff there is nothing left to replay
    (пустой хвост / an empty tail), so the server may close the reconnection immediately.
    """

    from_seq: int
    events: tuple[dict, ...]
    is_exhausted: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a stable three-key shape (orjson-serialisable / сериализуемо)."""
        return {
            "from_seq": self.from_seq,
            "events": list(self.events),
            "is_exhausted": self.is_exhausted,
        }


def resume_after(events: list[dict], last_event_id: int | None) -> ResumeSlice:
    """Replay every event with ``seq > last_event_id`` (повтор хвоста после ``Last-Event-ID``).

    ``events`` is stamped via :func:`index_events` (input never mutated). When ``last_event_id``
    is ``None`` or negative the whole stream is replayed from ``seq == 0`` (полный повтор / a
    full replay — a fresh connection with no prior id). Otherwise only events strictly after the
    id are returned, so an id at (or beyond) the last ``seq`` yields an empty slice. ``from_seq``
    is ``last_event_id + 1`` clamped to ``0``; ``is_exhausted`` is ``True`` iff the slice is
    empty.
    """
    indexed = index_events(events)
    if last_event_id is None or last_event_id < 0:
        from_seq = 0
        tail = tuple(indexed)
    else:
        from_seq = last_event_id + 1
        tail = tuple(event for event in indexed if event["seq"] > last_event_id)
    return ResumeSlice(from_seq=from_seq, events=tail, is_exhausted=len(tail) == 0)
