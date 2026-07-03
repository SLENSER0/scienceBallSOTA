"""Chat session + message store (§14.4)."""

from __future__ import annotations

import pytest

from kg_common.storage.chat_sessions import ChatMessage, ChatSession, ChatStore


@pytest.fixture
def store() -> ChatStore:
    s = ChatStore("sqlite:///:memory:")
    s.migrate()
    return s


def test_create_and_get_session(store: ChatStore) -> None:
    created = store.create_session("sess:1", user_id="u:1", title="Диалог")
    assert isinstance(created, ChatSession)
    got = store.get_session("sess:1")
    assert got is not None
    assert got.session_id == "sess:1"
    assert got.user_id == "u:1"
    assert got.title == "Диалог"
    assert got.created_at != ""  # timestamp stamped on create
    assert got.as_dict()["title"] == "Диалог"


def test_get_missing_session_returns_none(store: ChatStore) -> None:
    assert store.get_session("nope") is None


def test_add_messages_seq_auto_increments(store: ChatStore) -> None:
    store.create_session("s", user_id="u")
    s0 = store.add_message("s", "user", "привет", "m0")
    s1 = store.add_message("s", "assistant", "hi", "m1")
    s2 = store.add_message("s", "user", "как дела", "m2")
    assert (s0, s1, s2) == (0, 1, 2)


def test_messages_returned_in_seq_order(store: ChatStore) -> None:
    store.create_session("s", user_id="u")
    # insert out of natural order using explicit seq; messages() must sort by seq
    store.add_message("s", "user", "third", "m2", seq=2)
    store.add_message("s", "user", "first", "m0", seq=0)
    store.add_message("s", "user", "second", "m1", seq=1)
    msgs = store.messages("s")
    assert [m.content for m in msgs] == ["first", "second", "third"]
    assert [m.seq for m in msgs] == [0, 1, 2]
    assert all(isinstance(m, ChatMessage) for m in msgs)


def test_seq_is_per_session_not_global(store: ChatStore) -> None:
    store.create_session("a", user_id="u")
    store.create_session("b", user_id="u")
    assert store.add_message("a", "user", "x", "a0") == 0
    assert store.add_message("b", "user", "y", "b0") == 0  # b restarts at 0
    assert store.add_message("a", "user", "z", "a1") == 1


def test_list_sessions_by_user_and_all(store: ChatStore) -> None:
    store.create_session("s1", user_id="alice")
    store.create_session("s2", user_id="alice")
    store.create_session("s3", user_id="bob")
    alice = store.list_sessions(user_id="alice")
    assert {s.session_id for s in alice} == {"s1", "s2"}
    assert {s.session_id for s in store.list_sessions()} == {"s1", "s2", "s3"}


def test_delete_session_cascades_messages(store: ChatStore) -> None:
    store.create_session("s", user_id="u")
    store.add_message("s", "user", "a", "m0")
    store.add_message("s", "user", "b", "m1")
    assert len(store.messages("s")) == 2
    store.delete_session("s")
    assert store.get_session("s") is None
    assert store.messages("s") == []  # cascade removed the messages


def test_create_session_is_idempotent_upsert(store: ChatStore) -> None:
    first = store.create_session("s", user_id="u", title="old")
    updated = store.create_session("s", user_id="u", title="new")  # UPSERT by PK
    assert len(store.list_sessions()) == 1
    assert updated.title == "new"
    assert updated.created_at == first.created_at  # created_at preserved


def test_add_message_is_idempotent_by_pk(store: ChatStore) -> None:
    store.create_session("s", user_id="u")
    seq_a = store.add_message("s", "user", "draft", "m0")
    seq_b = store.add_message("s", "user", "edited", "m0")  # same message_id
    assert seq_a == seq_b == 0
    msgs = store.messages("s")
    assert len(msgs) == 1
    assert msgs[0].content == "edited"  # content updated, no duplicate row


def test_empty_session_has_no_messages(store: ChatStore) -> None:
    store.create_session("s", user_id="u")
    assert store.messages("s") == []
    assert store.messages("does-not-exist") == []
