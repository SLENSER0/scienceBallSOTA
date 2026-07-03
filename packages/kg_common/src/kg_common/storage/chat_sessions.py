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

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
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
        # re-create by PK updates user_id/title; created_at stays as first insert
        stmt = stmt.on_conflict_do_update(
            index_elements=["session_id"],
            set_={"user_id": stmt.excluded.user_id, "title": stmt.excluded.title},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        got = self.get_session(session_id)
        assert got is not None  # just inserted
        return got

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
        """
        with self.engine.begin() as conn:
            if seq is None:
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
        return seq

    def messages(self, session_id: str) -> list[ChatMessage]:
        """Return the session's messages ordered by ``seq`` (turn order, §14.4)."""
        q = (
            select(chat_messages)
            .where(chat_messages.c.session_id == session_id)
            .order_by(chat_messages.c.seq, chat_messages.c.message_id)
        )
        with self.engine.begin() as conn:
            return [ChatMessage(**r._mapping) for r in conn.execute(q).all()]
