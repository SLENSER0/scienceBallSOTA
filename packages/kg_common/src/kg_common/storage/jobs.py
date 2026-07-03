"""Ingest/pipeline job status store (§5.6 job status, §14.10 ``/ingest/jobs``).

Persists the lifecycle of an ingestion/pipeline *задача* (job) so the API
facade ``GET /api/v1/ingest/jobs/{job_id}`` and the orchestrator can report
*статус* (status), *прогресс* (progress) and *ошибки* (errors) back to the UI.

Same backend-agnostic SQLAlchemy design as
:class:`~kg_common.storage.sql.SqlMetaStore`,
:class:`~kg_common.storage.source_registry.SourceRegistry` and
:class:`~kg_common.storage.chat_sessions.ChatStore`: it reuses the shared engine
and ``MetaData`` plus the dialect-native ``INSERT ... ON CONFLICT`` (SQLite ≥3.24
and Postgres) so re-creating a job by primary key is idempotent. Works identically
over the embedded SQLite profile and the Postgres server profile.

``progress`` is always the recomputed ``done / total`` fraction, clamped to the
closed interval ``[0.0, 1.0]`` (an over-count where ``done > total`` saturates at
``1.0``; a zero/negative ``total`` yields ``0.0`` instead of dividing by zero).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Table,
    select,
    update,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- lifecycle statuses (§5.6) --------------------------------------------
#: Ordered job lifecycle: queued → running → (succeeded | failed | cancelled).
VALID_STATUSES: frozenset[str] = frozenset(
    {"queued", "running", "succeeded", "failed", "cancelled"}
)

# -- schema (§14.10 /ingest/jobs) -----------------------------------------
jobs = Table(
    "jobs",
    _metadata,
    Column("job_id", String, primary_key=True),
    Column("kind", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="queued"),
    Column("progress", Float, nullable=False, default=0.0),
    Column("total", Integer, nullable=False, default=0),
    Column("done", Integer, nullable=False, default=0),
    Column("error", String, nullable=True),
    Column("created_at", String, nullable=False, default=""),
    Column("updated_at", String, nullable=False, default=""),
)


def _now() -> str:
    """Current UTC timestamp as an ISO-8601 string (portable across backends)."""
    return datetime.now(UTC).isoformat()


def _fraction(done: int, total: int) -> float:
    """Recompute ``done / total`` clamped to ``[0.0, 1.0]`` (§5.6 progress).

    A zero/negative ``total`` returns ``0.0`` (no division by zero); an over-count
    where ``done > total`` saturates at ``1.0``; a negative ``done`` floors at ``0.0``.
    """
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, done / total))


def _check_status(status: str) -> str:
    """Validate ``status`` against :data:`VALID_STATUSES` (§5.6)."""
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown job status: {status!r} (allowed: {sorted(VALID_STATUSES)})")
    return status


@dataclass(frozen=True)
class Job:
    """One ingest/pipeline job — задача (§5.6 job status)."""

    job_id: str
    kind: str = ""
    status: str = "queued"
    progress: float = 0.0
    total: int = 0
    done: int = 0
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Serialize for the ``/ingest/jobs`` JSON response (§14.10)."""
        return asdict(self)


class JobStore:
    """Ingest job status store over any SQLAlchemy URL (SQLite / Postgres)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Idempotently create the ``jobs`` table (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- create -----------------------------------------------------------
    def create_job(self, job_id: str, kind: str, total: int = 0) -> Job:
        """Create a ``queued`` job (§5.6); re-create by ``job_id`` is a no-op UPSERT."""
        now = _now()
        stmt = self._insert(jobs).values(
            job_id=job_id,
            kind=kind,
            status="queued",
            progress=0.0,
            total=int(total),
            done=0,
            error=None,
            created_at=now,
            updated_at=now,
        )
        # re-create by PK is idempotent: keep the original row untouched
        stmt = stmt.on_conflict_do_nothing(index_elements=["job_id"])
        with self.engine.begin() as conn:
            conn.execute(stmt)
        got = self.get_job(job_id)
        assert got is not None  # just inserted
        return got

    # -- mutate -----------------------------------------------------------
    def update_progress(self, job_id: str, done: int, status: str | None = None) -> Job | None:
        """Set ``done`` and recompute ``progress = done / total`` clamped to ``[0, 1]``.

        Optionally transition ``status`` in the same write (§5.6). Returns the updated
        :class:`Job`, or ``None`` if ``job_id`` is unknown.
        """
        job = self.get_job(job_id)
        if job is None:
            return None
        values: dict[str, Any] = {
            "done": int(done),
            "progress": _fraction(int(done), job.total),
            "updated_at": _now(),
        }
        if status is not None:
            values["status"] = _check_status(status)
        with self.engine.begin() as conn:
            conn.execute(update(jobs).where(jobs.c.job_id == job_id).values(**values))
        return self.get_job(job_id)

    def set_status(self, job_id: str, status: str, error: str | None = None) -> Job | None:
        """Transition a job's ``status`` (and optional ``error`` text); §5.6.

        Returns the updated :class:`Job`, or ``None`` if ``job_id`` is unknown.
        """
        _check_status(status)
        with self.engine.begin() as conn:
            res = conn.execute(
                update(jobs)
                .where(jobs.c.job_id == job_id)
                .values(status=status, error=error, updated_at=_now())
            )
            if res.rowcount == 0:
                return None
        return self.get_job(job_id)

    def cancel(self, job_id: str) -> Job | None:
        """Cancel a job — set ``status='cancelled'`` (§5.6). Returns the updated Job."""
        return self.set_status(job_id, "cancelled")

    # -- read -------------------------------------------------------------
    def get_job(self, job_id: str) -> Job | None:
        """Fetch one job by ``job_id`` (§14.10), or ``None`` if absent."""
        q = select(jobs).where(jobs.c.job_id == job_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return Job(**row._mapping) if row else None

    def list_jobs(self, status: str | None = None, kind: str | None = None) -> list[Job]:
        """List jobs (optionally filtered by ``status`` and/or ``kind``), oldest first."""
        q = select(jobs)
        if status is not None:
            q = q.where(jobs.c.status == status)
        if kind is not None:
            q = q.where(jobs.c.kind == kind)
        q = q.order_by(jobs.c.created_at, jobs.c.job_id)
        with self.engine.begin() as conn:
            return [Job(**r._mapping) for r in conn.execute(q).all()]
