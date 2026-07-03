"""§13.22 tests — consumer-side invariant validation of a received stream.

Каждый тест собран вручную / every fixture is a hand-built wire sequence, so the
expected verdict is checkable by eye against the §13.22 invariants.
"""

from __future__ import annotations

from agent_service.stream_invariants import KNOWN_TYPES, StreamCheck, check_stream


def _ev(etype: str, **data: object) -> dict[str, object]:
    """Build a ``{'type', 'data'}`` wire frame (тестовый кадр / test frame)."""
    return {"type": etype, "data": dict(data)}


def test_wellformed_stream_ok() -> None:
    events = [
        _ev("tool_start", tool="search"),
        _ev("tool_end", tool="search"),
        _ev("evidence", count=2),
        _ev("done"),
    ]
    result = check_stream(events)
    assert result.ok is True
    assert result.problems == ()


def test_missing_done_is_problem() -> None:
    events = [
        _ev("tool_start", tool="search"),
        _ev("tool_end", tool="search"),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("done" in p for p in result.problems)


def test_done_not_last_is_problem() -> None:
    events = [
        _ev("done"),
        _ev("evidence", count=1),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("last" in p for p in result.problems)


def test_tool_end_without_start_is_problem() -> None:
    events = [
        _ev("tool_end", tool="orphan"),
        _ev("done"),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("orphan" in p and "tool_start" in p for p in result.problems)


def test_two_done_events_is_problem() -> None:
    events = [
        _ev("token"),
        _ev("done"),
        _ev("done"),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("exactly one" in p for p in result.problems)


def test_event_after_done_is_problem() -> None:
    events = [
        _ev("token"),
        _ev("done"),
        _ev("evidence", count=1),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("follows terminal 'done'" in p for p in result.problems)


def test_unknown_type_is_problem() -> None:
    events = [
        _ev("frobnicate"),
        _ev("done"),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("frobnicate" in p and "unknown" in p for p in result.problems)


def test_token_after_done_is_problem() -> None:
    # 'done' not last already flags ordering; the token-after-done rule adds its own.
    events = [
        _ev("done"),
        _ev("token"),
    ]
    result = check_stream(events)
    assert result.ok is False
    assert any("'token' occurs after terminal 'done'" in p for p in result.problems)


def test_as_dict_problems_is_list() -> None:
    result = check_stream([_ev("frobnicate"), _ev("done")])
    d = result.as_dict()
    assert isinstance(d["problems"], list)
    assert d["ok"] is False


def test_as_dict_ok_shape() -> None:
    result = check_stream([_ev("done")])
    assert result.as_dict() == {"ok": True, "problems": []}


def test_matched_tools_multiple_pairs_ok() -> None:
    events = [
        _ev("tool_start", tool="a"),
        _ev("tool_start", tool="b"),
        _ev("tool_end", tool="b"),
        _ev("tool_end", tool="a"),
        _ev("done"),
    ]
    assert check_stream(events).ok is True


def test_streamcheck_is_frozen() -> None:
    result = StreamCheck(ok=True, problems=())
    try:
        result.ok = False  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("StreamCheck should be frozen")


def test_known_types_union() -> None:
    assert "done" in KNOWN_TYPES
    assert "token" in KNOWN_TYPES
    assert "frobnicate" not in KNOWN_TYPES
