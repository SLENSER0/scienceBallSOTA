"""Hand-checked tests for §13.15 conversation memory.

Pure-python, no store / no LLM: drive :class:`ConversationMemory` directly and assert
exact turn contents, ordering, the token-budgeted context window (dropping oldest),
the ``max_turns`` sliding cap and the frozen :class:`Turn` serialisation. Every
expected value is spelled out so the test is verifiable by hand.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from agent_service.conversation_memory import (
    ConversationMemory,
    Turn,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# add_turn + recent
# ---------------------------------------------------------------------------
def test_add_turn_then_recent_returns_last_n_oldest_first() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "привет / hi")
    mem.add_turn("assistant", "здравствуйте / hello")
    mem.add_turn("user", "как дела / how are you")
    last_two = mem.recent(2)
    assert [t.content for t in last_two] == ["здравствуйте / hello", "как дела / how are you"]
    assert len(mem) == 3


def test_recent_over_ask_returns_all() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "one")
    mem.add_turn("assistant", "two")
    assert [t.content for t in mem.recent(10)] == ["one", "two"]


# ---------------------------------------------------------------------------
# role preserved / validated
# ---------------------------------------------------------------------------
def test_role_is_preserved() -> None:
    mem = ConversationMemory()
    mem.add_turn("system", "you are a lab assistant")
    mem.add_turn("user", "q")
    mem.add_turn("assistant", "a")
    assert [t.role for t in mem.turns] == ["system", "user", "assistant"]


def test_unknown_role_raises() -> None:
    mem = ConversationMemory()
    with pytest.raises(ValueError):
        mem.add_turn("robot", "beep")


# ---------------------------------------------------------------------------
# order is stable oldest -> newest
# ---------------------------------------------------------------------------
def test_order_oldest_to_newest() -> None:
    mem = ConversationMemory()
    for i in range(4):
        mem.add_turn("user", f"m{i}")
    assert [t.content for t in mem.turns] == ["m0", "m1", "m2", "m3"]


# ---------------------------------------------------------------------------
# empty memory
# ---------------------------------------------------------------------------
def test_empty_memory_views() -> None:
    mem = ConversationMemory()
    assert len(mem) == 0
    assert mem.recent(3) == []
    assert mem.context_window(100) == []
    assert mem.turns == []


def test_recent_non_positive_is_empty() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "x")
    assert mem.recent(0) == []
    assert mem.recent(-2) == []


# ---------------------------------------------------------------------------
# context_window truncates oldest by token budget
# ---------------------------------------------------------------------------
def test_context_window_truncates_oldest_by_tokens() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "a a a")  # 3 tokens (oldest)
    mem.add_turn("assistant", "b b")  # 2 tokens
    mem.add_turn("user", "c c c c")  # 4 tokens (newest)
    # budget 6 fits newest (4) + middle (2) = 6; the 3-token oldest is dropped.
    window = mem.context_window(6)
    assert [t.content for t in window] == ["b b", "c c c c"]


def test_context_window_keeps_all_when_budget_large() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "one two")  # 2
    mem.add_turn("assistant", "three")  # 1
    assert [t.content for t in mem.context_window(100)] == ["one two", "three"]


def test_context_window_single_over_budget_turn_excluded() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "w w w w w")  # 5 tokens, over a budget of 3
    assert mem.context_window(3) == []


def test_context_window_non_positive_budget_is_empty() -> None:
    mem = ConversationMemory()
    mem.add_turn("user", "hello world")
    assert mem.context_window(0) == []
    assert mem.context_window(-5) == []


# ---------------------------------------------------------------------------
# max_turns sliding cap
# ---------------------------------------------------------------------------
def test_max_turns_evicts_oldest() -> None:
    mem = ConversationMemory(max_turns=2)
    mem.add_turn("user", "t0")
    mem.add_turn("assistant", "t1")
    mem.add_turn("user", "t2")  # evicts t0
    assert [t.content for t in mem.turns] == ["t1", "t2"]
    assert len(mem) == 2


def test_max_turns_zero_keeps_nothing() -> None:
    mem = ConversationMemory(max_turns=0)
    mem.add_turn("user", "gone")
    assert mem.turns == []
    assert len(mem) == 0


def test_negative_max_turns_rejected() -> None:
    with pytest.raises(ValueError):
        ConversationMemory(max_turns=-1)


# ---------------------------------------------------------------------------
# Turn: frozen + serialisation
# ---------------------------------------------------------------------------
def test_turn_as_dict_exact_shape() -> None:
    t = Turn(role="user", content="привет / hi")
    assert t.as_dict() == {"role": "user", "content": "привет / hi"}


def test_turn_from_dict_round_trip() -> None:
    t = Turn(role="assistant", content="ответ / answer")
    assert Turn.from_dict(t.as_dict()) == t


def test_turn_token_estimate() -> None:
    assert Turn(role="user", content="a b c").token_estimate == 3
    assert Turn(role="user", content="").token_estimate == 0


def test_turn_is_frozen() -> None:
    t = Turn(role="user", content="x")
    with pytest.raises(FrozenInstanceError):
        t.content = "y"  # type: ignore[misc]


def test_estimate_tokens_helper() -> None:
    assert estimate_tokens("one two three") == 3
    assert estimate_tokens("   ") == 0
    assert estimate_tokens("") == 0


# ---------------------------------------------------------------------------
# memory as_dict
# ---------------------------------------------------------------------------
def test_memory_as_dict_shape() -> None:
    mem = ConversationMemory(max_turns=5)
    mem.add_turn("user", "q")
    mem.add_turn("assistant", "a")
    assert mem.as_dict() == {
        "max_turns": 5,
        "turns": [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ],
    }
