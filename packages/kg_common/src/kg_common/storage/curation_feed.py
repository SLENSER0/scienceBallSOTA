"""Curation activity feed (§16.9): лента курирующих событий (activity feed).

Каждое курирующее событие (`FeedEntry`) фиксирует одно действие куратора: кто
автор (`actor`), какое действие (`action`), над какой сущностью (`target_id`),
краткое человекочитаемое описание (`summary`) и явную метку времени
(`created_at`). Лента отдаётся «newest-first» — свежие события первыми, что
удобно для UI-ленты активности и audit-обзора.

Тот же backend-агностичный дизайн, что у MetaStore/DecisionStore (SQLite
embedded / Postgres server): переиспользуем движок и общую `MetaData`, запись
идемпотентна по `event_id` через dialect-native
``INSERT ... ON CONFLICT DO UPDATE`` (повторная запись того же события не плодит
дубликат, а обновляет поля — upsert). `created_at` передаётся явно (no wall
clock), поэтому порядок ленты детерминирован и тестируем.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import (
    Column,
    String,
    Table,
    func,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- schema (§16.9 curation activity feed) --------------------------------
curation_feed = Table(
    "curation_feed",
    _metadata,
    Column("event_id", String, primary_key=True),
    Column("actor", String, nullable=False, default=""),
    Column("action", String, nullable=False, default=""),
    Column("target_id", String, nullable=False, default=""),
    Column("summary", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
)


@dataclass(frozen=True)
class FeedEntry:
    """Одно событие ленты курирования — a single curation activity event (§16.9).

    `created_at` — явная ISO-8601 метка времени (задаётся вызывающим кодом, а не
    берётся из системных часов), поэтому «newest-first» порядок воспроизводим.
    RU/EN: событие / event, автор / actor, действие / action.
    """

    event_id: str
    actor: str = ""
    action: str = ""
    target_id: str = ""
    summary: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API-ленты / audit-лога)."""
        return asdict(self)


class CurationFeed:
    """Лента курирующих событий над любым SQLAlchemy URL (SQLite / Postgres)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # переиспользуем движок + общую MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Создать таблицы ленты (идемпотентно, rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- write ------------------------------------------------------------
    def record(
        self,
        event_id: str,
        actor: str,
        action: str,
        target_id: str,
        summary: str,
        created_at: str,
    ) -> FeedEntry:
        """Записать (или UPSERT по `event_id`) событие ленты; вернуть его.

        Идемпотентно по `event_id`: повторная запись того же id не создаёт
        дубликат, а обновляет поля (actor/action/target_id/summary/created_at) —
        upsert. `created_at` передаётся явно (no wall clock).
        """
        stmt = self._insert(curation_feed).values(
            event_id=event_id,
            actor=actor,
            action=action,
            target_id=target_id,
            summary=summary,
            created_at=created_at,
        )
        # повторный event_id обновляет поля (latest wins), без дубликата строки
        stmt = stmt.on_conflict_do_update(
            index_elements=["event_id"],
            set_={
                "actor": stmt.excluded.actor,
                "action": stmt.excluded.action,
                "target_id": stmt.excluded.target_id,
                "summary": stmt.excluded.summary,
                "created_at": stmt.excluded.created_at,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        return FeedEntry(
            event_id=event_id,
            actor=actor,
            action=action,
            target_id=target_id,
            summary=summary,
            created_at=created_at,
        )

    # -- read -------------------------------------------------------------
    def recent(
        self,
        *,
        limit: int = 50,
        actor: str | None = None,
        action: str | None = None,
    ) -> list[FeedEntry]:
        """Свежие события ленты, newest-first (по `created_at` убыв.).

        Тай-брейк по `event_id` убыв. — детерминированный порядок при равных
        `created_at`. Необязательные фильтры по `actor` и `action`; `limit`
        ограничивает число возвращаемых событий.
        """
        t = curation_feed
        q = select(t)
        if actor is not None:
            q = q.where(t.c.actor == actor)
        if action is not None:
            q = q.where(t.c.action == action)
        q = q.order_by(t.c.created_at.desc(), t.c.event_id.desc()).limit(limit)
        with self.engine.begin() as conn:
            return [self._row_to_entry(r) for r in conn.execute(q).all()]

    def count(self) -> int:
        """Общее число событий в ленте."""
        q = select(func.count()).select_from(curation_feed)
        with self.engine.begin() as conn:
            return int(conn.execute(q).scalar() or 0)

    @staticmethod
    def _row_to_entry(row: Any) -> FeedEntry:
        """Map a DB row to a :class:`FeedEntry`."""
        return FeedEntry(**row._mapping)
