"""Review-task assignment + load balancing (§16.10 назначение ревью / load balancing).

Persists the *назначение ревью* (review assignment): which reviewer owns which
review task. Each row (``task_id`` PK, ``assignee``, ``assigned_at``, ``status``)
lives in the ``review_assignment`` table. Same backend-agnostic SQLAlchemy design
as :class:`~kg_common.storage.sql.SqlMetaStore` and
:class:`~kg_common.storage.review_queue.ReviewQueue`: it reuses the shared engine +
``MetaData`` and the dialect-native ``INSERT ... ON CONFLICT DO UPDATE`` (SQLite
>=3.24 and Postgres), so re-assigning the same ``task_id`` never creates a
duplicate row — it upserts in place (idempotent).

Load balancing (§16.10 *балансировка нагрузки*): ``load_by_assignee`` returns the
per-reviewer count of *open* assignments and ``least_loaded`` picks the candidate
with the fewest open tasks (ties broken by candidate order, so the result is
deterministic and hand-checkable). Timestamps are always explicit — callers pass
``assigned_at`` / ``at`` — so the store never reads a hidden wall clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import Column, String, Table, func, select

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- status constants (an assignment is open until it is closed) -----------
STATUS_OPEN = "open"
STATUS_DONE = "done"

# -- schema (§16.10 review assignment) ------------------------------------
review_assignment = Table(
    "review_assignment",
    _metadata,
    Column("task_id", String, primary_key=True),
    Column("assignee", String, nullable=False, default=""),
    Column("assigned_at", String, nullable=False, default=""),
    Column("status", String, nullable=False, default=STATUS_OPEN),
)


@dataclass(frozen=True)
class Assignment:
    """One review-task assignment — назначение ревью (§16.10).

    ``task_id`` is the primary key: a task is owned by exactly one ``assignee`` at a
    time. ``status`` is ``open`` while the task counts toward the reviewer's load and
    ``done`` once it is closed (dropping out of load balancing).
    """

    task_id: str
    assignee: str = ""
    assigned_at: str = ""
    status: str = STATUS_OPEN

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReviewAssignment:
    """Review-assignment store over any SQLAlchemy URL (SQLite embedded / Postgres)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Idempotently create the review-assignment table (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- assign (idempotent upsert by task_id) ----------------------------
    def assign(self, task_id: str, assignee: str, assigned_at: str) -> None:
        """Assign ``task_id`` to ``assignee`` at ``assigned_at`` (§16.10).

        Upserts on the ``task_id`` primary key: re-assigning an existing task keeps
        the single row and refreshes ``assignee`` / ``assigned_at`` and re-opens it,
        so assigning the same task twice is idempotent (no duplicate rows).
        """
        stmt = self._insert(review_assignment).values(
            task_id=task_id,
            assignee=assignee,
            assigned_at=assigned_at,
            status=STATUS_OPEN,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["task_id"],
            set_={
                "assignee": stmt.excluded.assignee,
                "assigned_at": stmt.excluded.assigned_at,
                "status": stmt.excluded.status,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    # -- reassign (move an existing task to another reviewer) -------------
    def reassign(self, task_id: str, assignee: str, at: str) -> None:
        """Move existing ``task_id`` to ``assignee`` at ``at``, re-opening it (§16.10).

        A no-op if the task has never been assigned (updates only an existing row),
        so it never resurrects an unknown task. Used to rebalance load off a busy
        reviewer onto the ``least_loaded`` candidate.
        """
        stmt = (
            review_assignment.update()
            .where(review_assignment.c.task_id == task_id)
            .values(assignee=assignee, assigned_at=at, status=STATUS_OPEN)
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    # -- close (drop a task out of load balancing) ------------------------
    def close(self, task_id: str) -> None:
        """Close ``task_id`` (``open -> done``) so it stops counting toward load."""
        stmt = (
            review_assignment.update()
            .where(review_assignment.c.task_id == task_id)
            .values(status=STATUS_DONE)
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    # -- read -------------------------------------------------------------
    def assignments_for(self, assignee: str) -> list[Assignment]:
        """Return ``assignee``'s open worklist, oldest-first (``[]`` if none) (§16.10)."""
        t = review_assignment
        q = (
            select(t)
            .where(t.c.assignee == assignee, t.c.status == STATUS_OPEN)
            .order_by(t.c.assigned_at.asc(), t.c.task_id.asc())
        )
        with self.engine.begin() as conn:
            return [Assignment(**r._mapping) for r in conn.execute(q).all()]

    def load_by_assignee(self) -> dict[str, int]:
        """Return a ``{assignee: open_task_count}`` map over open assignments (§16.10)."""
        t = review_assignment
        q = (
            select(t.c.assignee, func.count())
            .where(t.c.status == STATUS_OPEN)
            .group_by(t.c.assignee)
        )
        with self.engine.begin() as conn:
            return {assignee: int(n) for assignee, n in conn.execute(q).all()}

    # -- load balancing ---------------------------------------------------
    def least_loaded(self, candidates: Sequence[str]) -> str:
        """Return the ``candidate`` with the fewest open tasks (§16.10 balancing).

        A candidate with no assignments counts as zero load. Ties are broken by the
        order of ``candidates`` (Python ``min`` keeps the first minimum), so the pick
        is deterministic. Guards empty input by returning ``""``.
        """
        if not candidates:
            return ""
        load = self.load_by_assignee()
        return min(candidates, key=lambda c: load.get(c, 0))
