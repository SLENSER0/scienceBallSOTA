"""Chat session + message store (§14.4)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import inspect

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


def test_migrate_creates_hot_query_indexes(store: ChatStore) -> None:
    """The composite indexes backing the hot per-session queries are created."""
    insp = inspect(store.engine)
    msg_idx = {i["name"]: i["column_names"] for i in insp.get_indexes("chat_messages")}
    sess_idx = {i["name"]: i["column_names"] for i in insp.get_indexes("chat_sessions")}
    assert msg_idx.get("ix_chat_messages_session_seq") == ["session_id", "seq"]
    assert sess_idx.get("ix_chat_sessions_user_created") == ["user_id", "created_at"]


def test_last_message_ats_matches_per_session_loop(store: ChatStore) -> None:
    """Batched last_message_ats == old per-session ``messages()[-1].created_at``."""
    store.create_session("s1", user_id="u")
    store.create_session("s2", user_id="u")
    store.create_session("empty", user_id="u")  # no messages -> absent from map
    store.add_message("s1", "user", "a", "s1m0")
    store.add_message("s1", "assistant", "b", "s1m1")
    store.add_message("s2", "user", "c", "s2m0")

    ids = ["s1", "s2", "empty"]
    batched = store.last_message_ats(ids)
    # reference: the pre-optimization per-session loop over messages()
    expected = {
        sid: store.messages(sid)[-1].created_at
        for sid in ids
        if store.messages(sid)  # empty session contributes nothing (as before)
    }
    assert batched == expected
    assert "empty" not in batched  # no rows -> caller falls back to session.created_at


def test_last_message_ats_empty_input(store: ChatStore) -> None:
    assert store.last_message_ats([]) == {}


def test_last_message_ats_only_requested_sessions(store: ChatStore) -> None:
    """The IN-filter scopes the aggregate to the requested session ids only."""
    store.create_session("a", user_id="u")
    store.create_session("b", user_id="u")
    store.add_message("a", "user", "x", "a0")
    store.add_message("b", "user", "y", "b0")
    got = store.last_message_ats(["a"])
    assert set(got) == {"a"}


def test_create_session_returning_row_matches_get_session(store: ChatStore) -> None:
    """create_session (RETURNING, one round-trip) returns the persisted row."""
    created = store.create_session("s", user_id="u", title="t")
    assert created == store.get_session("s")  # identical to the SELECT round-trip


def test_concurrent_add_message_no_duplicate_seq(tmp_path) -> None:
    """M-35: concurrent appends to one session must get unique, contiguous seqs.

    Uses a file-backed SQLite so all worker threads share one database (an
    in-memory URL would give each thread its own). Without serialization the
    read-max-then-insert races and two messages land on the same ``seq``.
    """
    url = f"sqlite:///{tmp_path / 'chat.db'}"
    store = ChatStore(url)
    store.migrate()
    store.create_session("s", user_id="u")

    n = 64

    def add(i: int) -> int:
        return store.add_message("s", "user", f"msg {i}", f"m{i}")

    with ThreadPoolExecutor(max_workers=16) as pool:
        seqs = sorted(pool.map(add, range(n)))

    # Every returned seq is unique and the set is exactly 0..n-1 (no dups/gaps).
    assert seqs == list(range(n))
    persisted = [m.seq for m in store.messages("s")]
    assert sorted(persisted) == list(range(n))
    assert len(set(persisted)) == n  # no duplicate seq persisted
