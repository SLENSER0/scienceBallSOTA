"""Pipeline-run registry (§9.7): records each pipeline *запуск* (run) + its stats.

Tracks every pipeline run — run_id, kind, status, when it *started*/*finished* and a
free-form ``stats`` JSON blob — so the orchestrator and the API can report *история
запусков* (run history) and per-run *статистика* (statistics) back to the UI.

Same backend-agnostic SQLAlchemy design as
:class:`~kg_common.storage.sql.SqlMetaStore`,
:class:`~kg_common.storage.jobs.JobStore` and
:class:`~kg_common.storage.source_registry.SourceRegistry`: it reuses the shared
engine and ``MetaData`` plus the dialect-native ``INSERT ... ON CONFLICT`` (SQLite
≥3.24 and Postgres), so re-recording a run by primary key is idempotent. Works
identically over the embedded SQLite profile and the Postgres server profile.

Timestamps are always passed in *explicitly* by the caller (ISO-8601 strings), never
generated inside the store — runs stay deterministic and hand-checkable in tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import (
    Column,
    String,
    Table,
    select,
    update,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- lifecycle statuses (§9.7) --------------------------------------------
#: Run lifecycle: running → (succeeded | failed | cancelled).
VALID_STATUSES: frozenset[str] = frozenset({"running", "succeeded", "failed", "cancelled"})

# -- schema (§9.7 pipeline_runs) ------------------------------------------
pipeline_runs = Table(
    "pipeline_runs",
    _metadata,
    Column("run_id", String, primary_key=True),
    Column("kind", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="running"),
    Column("started_at", String, nullable=False, default=""),
    Column("finished_at", String, nullable=True),
    Column("stats_json", String, nullable=False, default="{}"),
)


def _check_status(status: str) -> str:
    """Validate ``status`` against :data:`VALID_STATUSES` (§9.7)."""
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown run status: {status!r} (allowed: {sorted(VALID_STATUSES)})")
    return status


def _dumps(stats: dict[str, Any] | None) -> str:
    """Encode ``stats`` to deterministic JSON text (RU/EN kept as-is, keys sorted)."""
    return json.dumps(stats or {}, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class PipelineRun:
    """One pipeline run — запуск конвейера (§9.7).

    ``stats`` is the parsed dict (already decoded from the stored ``stats_json`` text),
    so callers work with structured data directly. ``finished_at`` is ``None`` until the
    run terminates via :meth:`RunRegistry.finish_run`.
    """

    run_id: str
    kind: str = ""
    status: str = "running"
    started_at: str = ""
    finished_at: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (stats kept as a nested dict)."""
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stats": dict(self.stats),
        }


class RunRegistry:
    """Pipeline-run registry over any SQLAlchemy URL (SQLite embedded / Postgres server)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        """Idempotently create the ``pipeline_runs`` table (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- record -----------------------------------------------------------
    def record_run(
        self,
        run_id: str,
        kind: str,
        started_at: str,
        *,
        status: str = "running",
        stats: dict[str, Any] | None = None,
    ) -> PipelineRun:
        """Record (or UPSERT by ``run_id``) a run start (§9.7).

        Idempotent: re-recording the same ``run_id`` refreshes kind/status/started_at/stats
        and clears ``finished_at`` (a re-record is a fresh start), never a duplicate row.
        """
        _check_status(status)
        stmt = self._insert(pipeline_runs).values(
            run_id=run_id,
            kind=kind,
            status=status,
            started_at=started_at,
            finished_at=None,
            stats_json=_dumps(stats),
        )
        # re-record by PK is a fresh start: overwrite fields, clear finished_at
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id"],
            set_={
                "kind": stmt.excluded.kind,
                "status": stmt.excluded.status,
                "started_at": stmt.excluded.started_at,
                "finished_at": stmt.excluded.finished_at,
                "stats_json": stmt.excluded.stats_json,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        got = self.get_run(run_id)
        assert got is not None  # just inserted
        return got

    # -- finish -----------------------------------------------------------
    def finish_run(
        self,
        run_id: str,
        finished_at: str,
        *,
        status: str = "succeeded",
        stats: dict[str, Any] | None = None,
    ) -> PipelineRun | None:
        """Terminate a run — set ``finished_at`` and ``status`` (§9.7).

        When ``stats`` is given it overwrites the stored blob (final counters); when it is
        ``None`` the existing ``stats`` are kept. Returns the updated :class:`PipelineRun`,
        or ``None`` if ``run_id`` is unknown.
        """
        _check_status(status)
        values: dict[str, Any] = {"status": status, "finished_at": finished_at}
        if stats is not None:
            values["stats_json"] = _dumps(stats)
        with self.engine.begin() as conn:
            res = conn.execute(
                update(pipeline_runs).where(pipeline_runs.c.run_id == run_id).values(**values)
            )
            if res.rowcount == 0:
                return None
        return self.get_run(run_id)

    # -- read -------------------------------------------------------------
    def get_run(self, run_id: str) -> PipelineRun | None:
        """Fetch one run by ``run_id`` (§9.7), or ``None`` if absent (stats parsed to dict)."""
        q = select(pipeline_runs).where(pipeline_runs.c.run_id == run_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return self._row_to_run(row) if row else None

    def recent(self, limit: int = 20, *, kind: str | None = None) -> list[PipelineRun]:
        """List runs newest-first by ``started_at`` (optionally filtered by ``kind``); §9.7.

        Ties on ``started_at`` break deterministically by descending ``run_id``. At most
        ``limit`` runs are returned.
        """
        q = select(pipeline_runs)
        if kind is not None:
            q = q.where(pipeline_runs.c.kind == kind)
        q = q.order_by(pipeline_runs.c.started_at.desc(), pipeline_runs.c.run_id.desc())
        q = q.limit(limit)
        with self.engine.begin() as conn:
            return [self._row_to_run(r) for r in conn.execute(q).all()]

    @staticmethod
    def _row_to_run(row: Any) -> PipelineRun:
        """Map a DB row to a :class:`PipelineRun`, decoding ``stats_json``."""
        m = row._mapping
        return PipelineRun(
            run_id=m["run_id"],
            kind=m["kind"],
            status=m["status"],
            started_at=m["started_at"],
            finished_at=m["finished_at"],
            stats=json.loads(m["stats_json"] or "{}"),
        )
