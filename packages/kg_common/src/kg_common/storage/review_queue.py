"""Review-task queue store (§16.4 review queue: repository, priorities, dedup, assignment).

Persists the curation *очередь ревью* (review queue): each *задача ревью*
(review task — task_id, target_id, kind, priority, status, assignee) is stored in
the ``review_tasks`` table. Same backend-agnostic SQLAlchemy design as
:class:`~kg_common.storage.sql.SqlMetaStore` and
:class:`~kg_common.storage.source_registry.SourceRegistry`: it reuses the shared
engine + ``MetaData`` and the dialect-native ``INSERT ... ON CONFLICT DO UPDATE``
(SQLite >=3.24 and Postgres) so re-enqueuing a task with the same ``dedup_key``
does not create a duplicate — instead it keeps the single existing task and may
raise its ``priority`` to the max of the old and new values (idempotent UPSERT).

The queue orders by (``priority`` desc, ``created_at`` asc): highest-priority,
oldest-first, matching the §16.4 acceptance criterion ("список очереди отсортирован
по priority desc, created_at asc"). ``assign`` moves a task ``open -> in_review``
and records the ``assignee``; ``resolve`` moves it to ``resolved`` so it drops out
of the open worklist (§16.4 transitions ``open -> in_review -> resolved``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Index,
    String,
    Table,
    UniqueConstraint,
    case,
    func,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- status constants (§16.4 transitions open -> in_review -> resolved) ----
STATUS_OPEN = "open"
STATUS_IN_REVIEW = "in_review"
STATUS_RESOLVED = "resolved"

# -- schema (§16.4 review queue) ------------------------------------------
review_tasks = Table(
    "review_tasks",
    _metadata,
    Column("task_id", String, primary_key=True),
    Column("target_id", String, nullable=False, default=""),
    Column("kind", String, nullable=False, default="low_confidence"),
    Column("priority", Float, nullable=False, default=0.0),
    Column("status", String, nullable=False, default=STATUS_OPEN),
    Column("assignee", String, nullable=False, default=""),
    Column("dedup_key", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
    UniqueConstraint("dedup_key", name="uq_review_dedup"),
)

# -- indexes (§16.4 queue polling on the running path) --------------------
# Serve ``next_tasks`` (open-queue listing) + ``counts_by_status`` without a
# full-table scan + filesort: WHERE status='open' ORDER BY priority desc,
# created_at asc, task_id asc is covered by a composite index whose column
# order matches the equality filter first, then the sort keys. Обслуживает
# опрос очереди без полного сканирования таблицы. ``create_all`` builds these
# alongside the table; the dedup UPSERT (on dedup_key) is unaffected.
Index(
    "ix_review_tasks_status_priority",
    review_tasks.c.status,
    review_tasks.c.priority.desc(),
    review_tasks.c.created_at,
    review_tasks.c.task_id,
)
# Per-reviewer worklist filter (``next_tasks(assignee=…)``): assignee + status.
Index(
    "ix_review_tasks_assignee_status",
    review_tasks.c.assignee,
    review_tasks.c.status,
)


def _now() -> str:
    """Current UTC timestamp as an ISO-8601 string (portable across backends)."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ReviewTask:
    """One review task — задача ревью (§16.4).

    ``dedup_key`` collapses duplicate auto-generated tasks for the same target: two
    enqueues with the same ``dedup_key`` yield a single row (the higher ``priority``
    wins). When left empty it falls back to ``task_id`` at enqueue time, so tasks
    without an explicit dedup key are never deduplicated against one another.
    """

    task_id: str
    target_id: str = ""
    kind: str = "low_confidence"
    priority: float = 0.0
    status: str = STATUS_OPEN
    assignee: str = ""
    dedup_key: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReviewQueue:
    """Review-task queue over any SQLAlchemy URL (SQLite embedded / Postgres server)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Idempotently create the review-queue table (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- enqueue (idempotent by dedup_key) --------------------------------
    def enqueue(self, task: ReviewTask) -> None:
        """Add ``task`` to the queue, deduplicating by ``dedup_key`` (§16.4).

        Re-enqueuing a task with an existing ``dedup_key`` does not create a
        duplicate: the single existing row is kept and its ``priority`` is raised
        to ``max(existing, new)`` (a portable CASE, so it works on both SQLite and
        Postgres). ``dedup_key`` falls back to ``task_id`` and ``created_at`` to the
        current UTC timestamp when either is left empty.
        """
        dedup_key = task.dedup_key or task.task_id
        created_at = task.created_at or _now()
        stmt = self._insert(review_tasks).values(
            task_id=task.task_id,
            target_id=task.target_id,
            kind=task.kind,
            priority=task.priority,
            status=task.status,
            assignee=task.assignee,
            dedup_key=dedup_key,
            created_at=created_at,
        )
        # keep the existing task; raise priority to the max of old/new (GREATEST)
        kept_priority = case(
            (review_tasks.c.priority >= stmt.excluded.priority, review_tasks.c.priority),
            else_=stmt.excluded.priority,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["dedup_key"],
            set_={"priority": kept_priority},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    # -- read -------------------------------------------------------------
    def get(self, task_id: str) -> ReviewTask | None:
        """Return a single task by ``task_id`` (or ``None`` if absent)."""
        q = select(review_tasks).where(review_tasks.c.task_id == task_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return ReviewTask(**row._mapping) if row else None

    def next_tasks(self, limit: int = 20, assignee: str | None = None) -> list[ReviewTask]:
        """Return open tasks by (``priority`` desc, ``created_at`` asc), capped at ``limit``.

        When ``assignee`` is given, only open tasks with that ``assignee`` are
        returned (the reviewer's own worklist); otherwise the whole open pool.
        """
        q = select(review_tasks).where(review_tasks.c.status == STATUS_OPEN)
        if assignee is not None:
            q = q.where(review_tasks.c.assignee == assignee)
        q = q.order_by(
            review_tasks.c.priority.desc(),
            review_tasks.c.created_at.asc(),
            review_tasks.c.task_id.asc(),
        ).limit(limit)
        with self.engine.begin() as conn:
            return [ReviewTask(**r._mapping) for r in conn.execute(q).all()]

    def counts_by_status(self) -> dict[str, int]:
        """Return a ``{status: count}`` histogram over all tasks (§16.4)."""
        q = select(review_tasks.c.status, func.count()).group_by(review_tasks.c.status)
        with self.engine.begin() as conn:
            return dict(conn.execute(q).all())

    # -- transitions (open -> in_review -> resolved) ----------------------
    def assign(self, task_id: str, assignee: str) -> None:
        """Assign ``task_id`` to ``assignee`` and move it ``open -> in_review`` (§16.4)."""
        stmt = (
            review_tasks.update()
            .where(review_tasks.c.task_id == task_id)
            .values(assignee=assignee, status=STATUS_IN_REVIEW)
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def resolve(self, task_id: str) -> None:
        """Resolve ``task_id`` so it drops out of the open worklist (§16.4)."""
        stmt = (
            review_tasks.update()
            .where(review_tasks.c.task_id == task_id)
            .values(status=STATUS_RESOLVED)
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
