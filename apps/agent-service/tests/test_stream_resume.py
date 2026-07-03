"""§13.22 tests for Last-Event-ID reconnect replay / тесты повтора хвоста потока.

Hand-checkable: a five-event stream is indexed and replayed under a range of
``Last-Event-ID`` values, and each expected slice is written out by hand.
"""

from __future__ import annotations

from itertools import pairwise

import orjson
from agent_service.stream_resume import ResumeSlice, index_events, resume_after


def _stream(n: int) -> list[dict]:
    """Build an ``n``-event ``{type, data}`` sequence (mimics build_stream_sequence output)."""
    return [{"type": "token", "data": {"i": i}} for i in range(n)]


def test_none_returns_all_from_zero() -> None:
    """Assertion 1: ``last_event_id=None`` replays the whole stream from ``from_seq==0``."""
    events = _stream(5)
    result = resume_after(events, None)
    assert result.from_seq == 0
    assert len(result.events) == 5
    assert not result.is_exhausted
    assert [e["seq"] for e in result.events] == [0, 1, 2, 3, 4]


def test_mid_stream_returns_tail() -> None:
    """Assertion 2: id=2 on a 5-event stream returns seq 3 and 4 (two events)."""
    result = resume_after(_stream(5), 2)
    assert result.from_seq == 3
    assert [e["seq"] for e in result.events] == [3, 4]
    assert len(result.events) == 2
    assert not result.is_exhausted


def test_last_seq_is_exhausted() -> None:
    """Assertion 3: id at the last seq yields an empty, exhausted slice."""
    result = resume_after(_stream(5), 4)
    assert result.events == ()
    assert result.is_exhausted
    assert result.from_seq == 5


def test_beyond_end_is_exhausted() -> None:
    """Assertion 4: an id past the end yields empty and exhausted."""
    result = resume_after(_stream(5), 99)
    assert result.events == ()
    assert result.is_exhausted
    assert result.from_seq == 100


def test_negative_behaves_like_none() -> None:
    """Assertion 5: a negative id is a full replay from seq 0 (like None)."""
    events = _stream(5)
    negative = resume_after(events, -1)
    none = resume_after(events, None)
    assert negative.from_seq == 0
    assert len(negative.events) == 5
    assert not negative.is_exhausted
    assert negative.as_dict() == none.as_dict()


def test_index_events_strictly_increasing_from_zero() -> None:
    """Assertion 6: index_events stamps strictly increasing seq starting at 0."""
    indexed = index_events(_stream(4))
    seqs = [e["seq"] for e in indexed]
    assert seqs == [0, 1, 2, 3]
    assert all(b > a for a, b in pairwise(seqs))


def test_events_preserve_order_and_content() -> None:
    """Assertion 7: returned events keep original order and content (plus seq)."""
    events = _stream(5)
    result = resume_after(events, 1)
    assert [e["type"] for e in result.events] == ["token", "token", "token"]
    assert [e["data"] for e in result.events] == [{"i": 2}, {"i": 3}, {"i": 4}]
    assert [e["seq"] for e in result.events] == [2, 3, 4]


def test_index_events_does_not_mutate_input() -> None:
    """index_events copies: the caller's dicts gain no ``seq`` key."""
    events = _stream(3)
    index_events(events)
    assert all("seq" not in e for e in events)


def test_as_dict_is_orjson_serialisable() -> None:
    """Assertion 8: ResumeSlice.as_dict round-trips through orjson."""
    result = resume_after(_stream(5), 2)
    raw = orjson.dumps(result.as_dict())
    restored = orjson.loads(raw)
    assert restored == {
        "from_seq": 3,
        "events": [
            {"type": "token", "data": {"i": 3}, "seq": 3},
            {"type": "token", "data": {"i": 4}, "seq": 4},
        ],
        "is_exhausted": False,
    }


def test_empty_stream_is_exhausted() -> None:
    """An empty stream is always exhausted, whatever the id."""
    result = resume_after([], None)
    assert result.events == ()
    assert result.is_exhausted
    assert result.from_seq == 0


def test_frozen_dataclass() -> None:
    """ResumeSlice is frozen: attributes cannot be reassigned."""
    result = ResumeSlice(from_seq=0, events=(), is_exhausted=True)
    try:
        result.from_seq = 5  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("ResumeSlice should be frozen")
