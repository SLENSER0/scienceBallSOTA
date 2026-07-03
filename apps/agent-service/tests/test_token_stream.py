"""Tests for §13.22 token delta assembler / сборщик дельт токенов."""

from __future__ import annotations

from agent_service.token_stream import (
    TokenStreamState,
    append_token,
    assemble,
    finalize,
    to_token_events,
)


def test_assemble_concatenates_deltas() -> None:
    """(1) assemble folds deltas into the joined text (Al-Cu)."""
    assert assemble(["Al", "-", "Cu"]) == "Al-Cu"


def test_assemble_empty_list_is_empty_string() -> None:
    """(2) an empty delta list yields the empty string (пустой поток)."""
    assert assemble([]) == ""


def test_append_token_twice_counts_two() -> None:
    """(3) two real deltas → count==2 and concatenated text."""
    state = append_token(TokenStreamState(), "a")
    state = append_token(state, "b")
    assert state.count == 2
    assert state.text == "ab"


def test_append_empty_delta_is_noop() -> None:
    """(4) an empty delta leaves text and count unchanged (no-op)."""
    start = TokenStreamState(text="hi", count=1)
    result = append_token(start, "")
    assert result.text == "hi"
    assert result.count == 1
    assert result is start  # same instance — ничего не пересобираем


def test_finalize_sets_done_preserving_text() -> None:
    """(5) finalize flips done True while keeping text/count."""
    state = append_token(TokenStreamState(), "done?")
    final = finalize(state)
    assert final.done is True
    assert final.text == "done?"
    assert final.count == 1
    assert state.done is False  # original untouched — frozen dataclass


def test_to_token_events_skips_empty_and_indexes_monotonically() -> None:
    """(6) empty deltas are dropped; indices stay gap-free (0, 1)."""
    events = to_token_events(["a", "", "b"])
    assert len(events) == 2
    assert [e["data"]["index"] for e in events] == [0, 1]


def test_to_token_events_type_and_exact_delta() -> None:
    """(7) each event is a token event carrying the exact delta text."""
    events = to_token_events(["Al", "", "-", "Cu"])
    assert [e["type"] for e in events] == ["token", "token", "token"]
    assert [e["data"]["text"] for e in events] == ["Al", "-", "Cu"]
    assert [e["data"]["index"] for e in events] == [0, 1, 2]


def test_as_dict_round_trips_fields() -> None:
    """(8) as_dict exposes text/count/done verbatim."""
    state = finalize(append_token(TokenStreamState(), "x"))
    assert state.as_dict() == {"text": "x", "count": 1, "done": True}
