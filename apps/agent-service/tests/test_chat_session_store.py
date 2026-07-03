"""§13.24 тесты in-memory chat-session store / chat_session_store tests."""

from __future__ import annotations

import pytest
from agent_service.chat_session_store import (
    ChatSession,
    append_message,
    last_user_message,
    message_count,
    new_session,
)


def test_new_session_is_empty() -> None:
    """(1) new_session даёт пустые messages и message_count==0."""
    session = new_session("s1", "u1", now=100.0)
    assert isinstance(session, ChatSession)
    assert session.session_id == "s1"
    assert session.user_id == "u1"
    assert session.created_at == 100.0
    assert session.messages == ()
    assert message_count(session) == 0


def test_append_returns_new_object_original_unchanged() -> None:
    """(2) append возвращает новый объект, у оригинала message_count остаётся 0."""
    session = new_session("s1", "u1", now=100.0)
    updated = append_message(session, "user", "hello", "m1", now=101.0)
    assert updated is not session
    assert message_count(updated) == 1
    # Оригинал не тронут / original untouched.
    assert message_count(session) == 0
    assert session.messages == ()


def test_append_rejects_unknown_role() -> None:
    """(3) append с role='bot' поднимает ValueError."""
    session = new_session("s1", "u1", now=100.0)
    with pytest.raises(ValueError):
        append_message(session, "bot", "beep", "m1", now=101.0)


def test_two_appends_preserve_order() -> None:
    """(4) два последовательных append сохраняют порядок и message_count==2."""
    session = new_session("s1", "u1", now=100.0)
    session = append_message(session, "user", "first", "m1", now=101.0)
    session = append_message(session, "assistant", "second", "m2", now=102.0)
    assert message_count(session) == 2
    assert session.messages[0].message_id == "m1"
    assert session.messages[0].content == "first"
    assert session.messages[1].message_id == "m2"
    assert session.messages[1].content == "second"


def test_last_user_message_returns_most_recent_user() -> None:
    """(5) last_user_message возвращает последнее role=='user' сообщение."""
    session = new_session("s1", "u1", now=100.0)
    assert last_user_message(session) is None

    session = append_message(session, "user", "q1", "m1", now=101.0)
    session = append_message(session, "assistant", "a1", "m2", now=102.0)
    session = append_message(session, "user", "q2", "m3", now=103.0)
    # Последнее сообщение после самого позднего user / trailing assistant reply.
    session = append_message(session, "assistant", "a2", "m4", now=104.0)

    last = last_user_message(session)
    assert last is not None
    assert last.message_id == "m3"
    assert last.content == "q2"


def test_last_user_message_none_when_no_user() -> None:
    """(5) last_user_message даёт None, когда нет ни одного user-сообщения."""
    session = new_session("s1", "u1", now=100.0)
    session = append_message(session, "assistant", "hi", "m1", now=101.0)
    session = append_message(session, "system", "sys", "m2", now=102.0)
    assert last_user_message(session) is None


def test_as_dict_projects_messages_to_dicts() -> None:
    """(6) as_dict()['messages'] — список dict-ов с 'created_at' и 'role'."""
    session = new_session("s1", "u1", now=100.0)
    session = append_message(session, "user", "hello", "m1", now=101.0)
    session = append_message(session, "assistant", "hi there", "m2", now=102.0)

    payload = session.as_dict()
    assert payload["session_id"] == "s1"
    assert payload["user_id"] == "u1"
    assert payload["created_at"] == 100.0

    messages = payload["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    for msg in messages:
        assert isinstance(msg, dict)
        assert "created_at" in msg
        assert "role" in msg
    assert messages[0]["role"] == "user"
    assert messages[0]["created_at"] == 101.0
    assert messages[1]["role"] == "assistant"


def test_message_as_dict_roundtrip() -> None:
    """ChatMessage.as_dict содержит все поля / message projection carries all fields."""
    session = new_session("s1", "u1", now=100.0)
    session = append_message(session, "system", "ctx", "m1", now=101.5)
    msg_dict = session.messages[0].as_dict()
    assert msg_dict == {
        "message_id": "m1",
        "role": "system",
        "content": "ctx",
        "created_at": 101.5,
    }
