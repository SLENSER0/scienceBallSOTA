"""Saved views + user settings store (§14.15 /views, /me/settings).

Persists two bits of per-user UI state: *сохранённые виды* (saved views —
a named, typed JSON payload describing a graph/table/query view) and
*настройки пользователя* (user settings — a single JSON blob per user).
Same backend-agnostic SQLAlchemy design as
:class:`~kg_common.storage.sql.SqlMetaStore`,
:class:`~kg_common.storage.source_registry.SourceRegistry` and
:class:`~kg_common.storage.chat_sessions.ChatStore`: it reuses the shared
engine + ``MetaData`` and the dialect-native
``INSERT ... ON CONFLICT DO UPDATE`` (SQLite ≥3.24 and Postgres), so
re-saving a view by ``view_id`` or re-setting a user's settings updates the
existing row rather than duplicating (idempotent UPSERT). Dict payloads are
serialised as JSON text so the same schema is portable across both backends
(no native JSON column type required).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    String,
    Table,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- schema (§14.15 /views, /me/settings) ---------------------------------
saved_views = Table(
    "saved_views",
    _metadata,
    Column("view_id", String, primary_key=True),
    Column("user_id", String, nullable=False, default=""),
    Column("name", String, nullable=False, default=""),
    Column("kind", String, nullable=False, default=""),
    Column("payload_json", String, nullable=False, default="{}"),
    Column("created_at", String, nullable=False, default=""),
)

user_settings = Table(
    "user_settings",
    _metadata,
    Column("user_id", String, primary_key=True),
    Column("settings_json", String, nullable=False, default="{}"),
)


def _now() -> str:
    """Current UTC timestamp as an ISO-8601 string (portable across backends)."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SavedView:
    """One saved view — сохранённый вид (§14.15).

    ``payload`` is the parsed dict (already decoded from the stored
    ``payload_json`` text), so callers work with structured data directly.
    """

    view_id: str
    user_id: str = ""
    name: str = ""
    kind: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (payload kept as a nested dict)."""
        return {
            "view_id": self.view_id,
            "user_id": self.user_id,
            "name": self.name,
            "kind": self.kind,
            "payload": dict(self.payload),
            "created_at": self.created_at,
        }


class ViewStore:
    """Saved-views + user-settings store over any SQLAlchemy URL (SQLite / Postgres)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Idempotently create the saved-views tables (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- saved views (§14.15 /views) --------------------------------------
    def save_view(
        self,
        view_id: str,
        user_id: str,
        name: str,
        kind: str,
        payload: dict[str, Any],
    ) -> SavedView:
        """Save (or UPSERT by ``view_id``) a view; keep original ``created_at``.

        Idempotent: re-saving the same ``view_id`` updates name/kind/payload
        but preserves the first-insert ``created_at`` timestamp.
        """
        stmt = self._insert(saved_views).values(
            view_id=view_id,
            user_id=user_id,
            name=name,
            kind=kind,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            created_at=_now(),
        )
        # re-save by PK updates fields; created_at stays as first insert
        stmt = stmt.on_conflict_do_update(
            index_elements=["view_id"],
            set_={
                "user_id": stmt.excluded.user_id,
                "name": stmt.excluded.name,
                "kind": stmt.excluded.kind,
                "payload_json": stmt.excluded.payload_json,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        got = self.get_view(view_id)
        assert got is not None  # just inserted
        return got

    def get_view(self, view_id: str) -> SavedView | None:
        """Fetch one view by id, or ``None`` if absent (payload parsed to dict)."""
        q = select(saved_views).where(saved_views.c.view_id == view_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return self._row_to_view(row) if row else None

    def list_views(self, user_id: str) -> list[SavedView]:
        """List a user's saved views, oldest first (deterministic tie-break by id)."""
        q = (
            select(saved_views)
            .where(saved_views.c.user_id == user_id)
            .order_by(saved_views.c.created_at, saved_views.c.view_id)
        )
        with self.engine.begin() as conn:
            return [self._row_to_view(r) for r in conn.execute(q).all()]

    def delete_view(self, view_id: str) -> None:
        """Delete a view by id (no-op if it does not exist)."""
        with self.engine.begin() as conn:
            conn.execute(saved_views.delete().where(saved_views.c.view_id == view_id))

    @staticmethod
    def _row_to_view(row: Any) -> SavedView:
        """Map a DB row to a :class:`SavedView`, decoding ``payload_json``."""
        m = row._mapping
        return SavedView(
            view_id=m["view_id"],
            user_id=m["user_id"],
            name=m["name"],
            kind=m["kind"],
            payload=json.loads(m["payload_json"] or "{}"),
            created_at=m["created_at"],
        )

    # -- user settings (§14.15 /me/settings) ------------------------------
    def set_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Replace a user's settings blob (UPSERT by ``user_id``); return it.

        This is a *replace*: the stored settings become exactly ``settings``.
        Use :meth:`update_settings` for a shallow key-merge instead.
        """
        stmt = self._insert(user_settings).values(
            user_id=user_id,
            settings_json=json.dumps(settings, ensure_ascii=False, sort_keys=True),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={"settings_json": stmt.excluded.settings_json},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        return self.get_settings(user_id)

    def get_settings(self, user_id: str) -> dict[str, Any]:
        """Return a user's settings dict (empty dict if never set — graceful)."""
        q = select(user_settings.c.settings_json).where(user_settings.c.user_id == user_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return json.loads(row.settings_json or "{}") if row else {}

    def update_settings(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Shallow-merge ``patch`` into a user's settings; return the merged dict.

        Existing keys not present in ``patch`` are preserved; keys in ``patch``
        overwrite. A convenience over :meth:`set_settings` (which replaces).
        """
        merged = {**self.get_settings(user_id), **patch}
        return self.set_settings(user_id, merged)
