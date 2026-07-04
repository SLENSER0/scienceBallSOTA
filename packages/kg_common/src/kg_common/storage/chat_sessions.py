"""Chat session + message store (§14.4 chat sessions resource).

Persists conversational state for the assistant UI: *сессии чата* (chat
sessions — session_id, user_id, title) and their ordered *сообщения*
(messages — role, content, per-session ``seq``). Same backend-agnostic
SQLAlchemy design as :class:`~kg_common.storage.sql.SqlMetaStore` and
:class:`~kg_common.storage.source_registry.SourceRegistry`: it reuses the
shared engine + ``MetaData`` and the dialect-native
``INSERT ... ON CONFLICT DO UPDATE`` (SQLite ≥3.24 and Postgres) so
re-creating a session or re-adding a message by primary key updates rather
than duplicates (idempotent UPSERT). ``add_message`` auto-increments a
per-session ``seq`` so ``messages`` can return the turn order deterministically;
``delete_session`` cascades to the session's messages (§14.4).
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    Index,
    Integer,
    String,
    Table,
    func,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- schema (§14.4 chat sessions resource) --------------------------------
chat_sessions = Table(
    "chat_sessions",
    _metadata,
    Column("session_id", String, primary_key=True),
    Column("user_id", String, nullable=False, default=""),
    Column("title", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
)

chat_messages = Table(
    "chat_messages",
    _metadata,
    Column("message_id", String, primary_key=True),
    Column("session_id", String, nullable=False, default=""),
    Column("role", String, nullable=False, default="user"),
    Column("content", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
    Column("seq", Integer, nullable=False, default=0),
)

# -- indexes (§14.4) ------------------------------------------------------
# Индексы под горячие запросы / indexes for the hot per-session queries.
# Every ``chat_messages`` read filters (and ``messages`` also orders) by
# ``session_id``; the composite ``(session_id, seq)`` lets ``messages`` satisfy
# both its WHERE and ORDER BY from the index, turns ``add_message``'s per-turn
# ``max(seq)`` into an index-tip lookup, and makes ``delete_session`` an index
# range instead of a full ``chat.db`` scan. ``list_sessions`` filters by
# ``user_id`` and orders by ``created_at``; ``(user_id, created_at)`` serves both.
# Attached to the shared MetaData, so migrate() -> _metadata.create_all emits
# them idempotently (CREATE INDEX IF NOT EXISTS) — no migrate() change needed.
Index("ix_chat_messages_session_seq", chat_messages.c.session_id, chat_messages.c.seq)
Index("ix_chat_sessions_user_created", chat_sessions.c.user_id, chat_sessions.c.created_at)


def _now() -> str:
    """Current UTC timestamp as an ISO-8601 string (portable across backends)."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ChatSession:
    """One chat session — сессия чата (§14.4)."""

    session_id: str
    user_id: str = ""
    title: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatMessage:
    """One message within a session — сообщение (§14.4)."""

    message_id: str
    session_id: str
    role: str = "user"
    content: str = ""
    created_at: str = ""
    seq: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChatStore:
    """Chat session/message store over any SQLAlchemy URL (SQLite / Postgres)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)
        # Serializes the per-session ``seq`` read-max-then-insert in add_message so
        # concurrent appends to one session can't compute (and persist) the same
        # ``seq`` (M-35). One lock per store; the critical section is tiny.
        self._seq_lock = threading.Lock()

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Idempotently create the chat tables (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- sessions ---------------------------------------------------------
    def create_session(self, session_id: str, user_id: str = "", title: str = "") -> ChatSession:
        """Create (or UPSERT by ``session_id``) a session; keep original created_at."""
        created_at = _now()
        stmt = self._insert(chat_sessions).values(
            session_id=session_id,
            user_id=user_id,
            title=title,
            created_at=created_at,
        )
        # re-create by PK updates user_id/title; created_at stays as first insert.
        # RETURNING hands back the persisted row (post-upsert user_id/title, the
        # original created_at) in the SAME round-trip, so no second get_session
        # SELECT is needed. SQLite ≥3.35 and Postgres both support RETURNING with
        # ON CONFLICT DO UPDATE.
        stmt = stmt.on_conflict_do_update(
            index_elements=["session_id"],
            set_={"user_id": stmt.excluded.user_id, "title": stmt.excluded.title},
        ).returning(chat_sessions)
        with self.engine.begin() as conn:
            row = conn.execute(stmt).first()
        assert row is not None  # DO UPDATE always returns the persisted row
        return ChatSession(**row._mapping)

    def get_session(self, session_id: str) -> ChatSession | None:
        q = select(chat_sessions).where(chat_sessions.c.session_id == session_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return ChatSession(**row._mapping) if row else None

    def list_sessions(self, user_id: str | None = None) -> list[ChatSession]:
        """List sessions (all, or filtered by ``user_id``), oldest first."""
        q = select(chat_sessions)
        if user_id is not None:
            q = q.where(chat_sessions.c.user_id == user_id)
        q = q.order_by(chat_sessions.c.created_at, chat_sessions.c.session_id)
        with self.engine.begin() as conn:
            return [ChatSession(**r._mapping) for r in conn.execute(q).all()]

    def delete_session(self, session_id: str) -> None:
        """Delete a session and cascade-delete its messages (§14.4)."""
        with self.engine.begin() as conn:
            conn.execute(chat_messages.delete().where(chat_messages.c.session_id == session_id))
            conn.execute(chat_sessions.delete().where(chat_sessions.c.session_id == session_id))

    # -- messages ---------------------------------------------------------
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: str,
        seq: int | None = None,
    ) -> int:
        """Append (or UPSERT by ``message_id``) a message; return its ``seq``.

        When ``seq`` is ``None`` it auto-increments per session: the first
        message gets ``seq=0`` and each next one ``max(seq)+1``. Re-adding an
        existing ``message_id`` keeps that message's ``seq`` (idempotent).

        The auto-``seq`` read-max-then-insert is serialized under
        :attr:`_seq_lock` so concurrent appends to the same session can't read
        the same ``max(seq)`` and persist duplicate ``seq`` values (M-35). When
        the caller supplies an explicit ``seq`` no serialization is needed.
        """
        if seq is None:
            with self._seq_lock:
                return self._append_autoseq(session_id, role, content, message_id)
        return self._insert_message(session_id, role, content, message_id, seq)

    def _append_autoseq(
        self, session_id: str, role: str, content: str, message_id: str
    ) -> int:
        """Compute the next per-session ``seq`` and insert; caller holds the lock."""
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(chat_messages.c.seq).where(chat_messages.c.message_id == message_id)
            ).first()
            if existing is not None:
                seq = int(existing.seq)  # keep existing seq on re-add
            else:
                top = conn.execute(
                    select(func.max(chat_messages.c.seq)).where(
                        chat_messages.c.session_id == session_id
                    )
                ).scalar()
                seq = 0 if top is None else int(top) + 1
            self._exec_upsert(conn, session_id, role, content, message_id, seq)
        return seq

    def _insert_message(
        self, session_id: str, role: str, content: str, message_id: str, seq: int
    ) -> int:
        """Insert (UPSERT by ``message_id``) with an explicit ``seq``."""
        with self.engine.begin() as conn:
            self._exec_upsert(conn, session_id, role, content, message_id, seq)
        return seq

    def _exec_upsert(
        self, conn: Any, session_id: str, role: str, content: str, message_id: str, seq: int
    ) -> None:
        stmt = self._insert(chat_messages).values(
            message_id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=_now(),
            seq=seq,
        )
        # re-add by PK updates role/content/seq; created_at stays first insert
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "role": stmt.excluded.role,
                "content": stmt.excluded.content,
                "seq": stmt.excluded.seq,
            },
        )
        conn.execute(stmt)

    def messages(self, session_id: str) -> list[ChatMessage]:
        """Return the session's messages ordered by ``seq`` (turn order, §14.4)."""
        q = (
            select(chat_messages)
            .where(chat_messages.c.session_id == session_id)
            .order_by(chat_messages.c.seq, chat_messages.c.message_id)
        )
        with self.engine.begin() as conn:
            return [ChatMessage(**r._mapping) for r in conn.execute(q).all()]

    def last_message_ats(self, session_ids: list[str]) -> dict[str, str]:
        """Batched last-message timestamps — {session_id: max(created_at)} (§14.4).

        Одним сгруппированным запросом возвращает время последнего сообщения для
        каждой сессии из ``session_ids`` — без загрузки самих сообщений. Заменяет
        N вызовов :meth:`messages` (по одному на сессию) при рендере списка чатов.

        One grouped aggregate instead of an N+1 per-session scan: reads only the
        timestamps, never the (large) ``content`` payloads. ``created_at`` is
        stamped at insert time and rises with the append-only ``seq``, so
        ``max(created_at)`` equals the last-by-``seq`` message's ``created_at``.
        Sessions with no messages are simply absent from the returned mapping.
        """
        if not session_ids:
            return {}
        q = (
            select(chat_messages.c.session_id, func.max(chat_messages.c.created_at))
            .where(chat_messages.c.session_id.in_(session_ids))
            .group_by(chat_messages.c.session_id)
        )
        with self.engine.begin() as conn:
            return dict(conn.execute(q).all())
