"""Decision store (§16.7): версионирование и привязка решений к изменениям графа.

Каждое курирующее решение (`Decision`) фиксирует переход состояния сущности
(`target_id`): какое событие (`event_id`) и действие (`action`) его вызвало, кто
автор (`actor`), а также хэши состояния до/после (`before_hash`/`after_hash`).
Версии не удаляются («preserve previous versions», Step 7): для каждого `target_id`
`version` монотонно растёт (1, 2, 3, …), поэтому историю поля можно проследить
`значение → CurationEvent → Decision → actor`.

Тот же backend-агностичный дизайн, что и у MetaStore/SourceRegistry (SQLite
embedded / Postgres server): переиспользуем движок и общую MetaData, запись
идемпотентна по `decision_id` (повторная запись не плодит дубликатов и не
увеличивает версию).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata


def _now_iso() -> str:
    """Текущая метка времени UTC в ISO-8601 (`created_at`)."""
    return datetime.now(UTC).isoformat()


decisions = Table(
    "decisions",
    _metadata,
    Column("decision_id", String, primary_key=True),
    Column("target_id", String, nullable=False),
    Column("event_id", String, nullable=False, default=""),
    Column("action", String, nullable=False, default=""),
    Column("actor", String, nullable=False, default=""),
    Column("before_hash", String, nullable=False, default=""),
    Column("after_hash", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
    Column("version", Integer, nullable=False, default=1),
    # версии per-target уникальны — не бывает двух решений одной версии на сущность
    UniqueConstraint("target_id", "version", name="uq_decision_target_version"),
)


@dataclass(frozen=True)
class Decision:
    """Курирующее решение, привязанное к изменению графа (§16.7).

    `version` присваивается хранилищем (`DecisionStore.record_decision`) по
    `target_id`; значение в переданном объекте игнорируется — возвращается копия
    с фактической версией. RU/EN: решение / decision, автор / actor.
    """

    decision_id: str
    target_id: str
    event_id: str = ""
    action: str = ""
    actor: str = ""
    before_hash: str = ""
    after_hash: str = ""
    created_at: str = field(default_factory=_now_iso)
    version: int = 1

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога)."""
        return asdict(self)


class DecisionStore:
    """Хранилище решений над любым SQLAlchemy URL (SQLite embedded / Postgres)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # переиспользуем движок + общую MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    def migrate(self) -> None:
        """Создать таблицы (идемпотентно, rollback-safe)."""
        _metadata.create_all(self.engine)

    @staticmethod
    def _row_to_decision(row: Any) -> Decision:
        return Decision(**row._mapping)

    def record_decision(self, decision: Decision) -> Decision:
        """Записать решение; вернуть сохранённую версию.

        Идемпотентно по `decision_id`: повторная запись того же id не создаёт
        дубликат и не увеличивает версию — возвращается уже сохранённое решение.
        Для нового id `version = max(version по target_id) + 1` (начиная с 1).
        """
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(decisions).where(decisions.c.decision_id == decision.decision_id)
            ).first()
            if existing is not None:
                return self._row_to_decision(existing)

            max_v = conn.execute(
                select(func.max(decisions.c.version)).where(
                    decisions.c.target_id == decision.target_id
                )
            ).scalar()
            version = int(max_v or 0) + 1
            created_at = decision.created_at or _now_iso()

            stmt = self._insert(decisions).values(
                decision_id=decision.decision_id,
                target_id=decision.target_id,
                event_id=decision.event_id,
                action=decision.action,
                actor=decision.actor,
                before_hash=decision.before_hash,
                after_hash=decision.after_hash,
                created_at=created_at,
                version=version,
            )
            # belt-and-suspenders: параллельная повторная запись id не падает
            stmt = stmt.on_conflict_do_nothing(index_elements=["decision_id"])
            conn.execute(stmt)
        return replace(decision, created_at=created_at, version=version)

    def history_for(self, target_id: str) -> list[Decision]:
        """Все решения по сущности, упорядоченные по возрастанию `version`."""
        q = (
            select(decisions)
            .where(decisions.c.target_id == target_id)
            .order_by(decisions.c.version)
        )
        with self.engine.begin() as conn:
            return [self._row_to_decision(r) for r in conn.execute(q).all()]

    def latest_for(self, target_id: str) -> Decision | None:
        """Решение с наибольшей версией по сущности (или ``None``)."""
        q = (
            select(decisions)
            .where(decisions.c.target_id == target_id)
            .order_by(decisions.c.version.desc())
            .limit(1)
        )
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return self._row_to_decision(row) if row else None

    def list_by_actor(self, actor: str) -> list[Decision]:
        """Все решения автора, упорядоченные по `target_id`, затем `version`."""
        q = (
            select(decisions)
            .where(decisions.c.actor == actor)
            .order_by(decisions.c.target_id, decisions.c.version)
        )
        with self.engine.begin() as conn:
            return [self._row_to_decision(r) for r in conn.execute(q).all()]
