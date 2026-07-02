"""SQLAlchemy MetaStore — identical code for SQLite and PostgreSQL (§25.4).

The two backends differ only by connection URL; tables, UPSERT keys and queries
are shared, so ``coverage_stats`` / ``get_recall_priors`` are byte-for-byte
identical across backends (parity tests in ``test_storage.py``). UPSERT uses the
dialect-native ``INSERT ... ON CONFLICT DO UPDATE`` (both SQLite ≥3.24 and
Postgres support it) so re-logging the same coverage event is idempotent.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    case,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine

from kg_common.storage.base import (
    CoverageEvent,
    CoverageStats,
    RecallPrior,
)

_metadata = MetaData()

extraction_coverage = Table(
    "extraction_coverage",
    _metadata,
    Column("doc_id", String, nullable=False),
    Column("chunk_id", String, nullable=False),
    Column("extractor", String, nullable=False),
    Column("target_type", String, nullable=False),
    Column("attempted", Boolean, nullable=False, default=True),
    Column("found_count", Integer, nullable=False, default=0),
    Column("run_id", String, nullable=False, default="unspecified"),
    UniqueConstraint(
        "doc_id", "chunk_id", "extractor", "target_type", name="uq_coverage_key"
    ),
)

extractor_recall = Table(
    "extractor_recall",
    _metadata,
    Column("extractor", String, nullable=False),
    Column("target_type", String, nullable=False),
    Column("recall", Float, nullable=False),
    Column("sample_size", Integer, nullable=False, default=0),
    UniqueConstraint("extractor", "target_type", name="uq_recall_key"),
)


def _dialect_insert(engine: Engine):  # type: ignore[no-untyped-def]
    """Return the dialect-specific ``insert`` supporting ``on_conflict_do_update``."""
    name = engine.dialect.name
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert
    # sqlite (embedded) and anything else supporting ON CONFLICT
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    return sqlite_insert


class SqlMetaStore:
    """Concrete :class:`~kg_common.storage.base.MetaStore` over any SQLAlchemy URL."""

    def __init__(self, url: str = "sqlite:///:memory:", *, echo: bool = False) -> None:
        # check_same_thread off so a file SQLite store is usable from the API + workers
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(url, echo=echo, connect_args=connect_args)
        self._insert = _dialect_insert(self.engine)

    # -- schema -----------------------------------------------------------
    def migrate(self) -> None:
        _metadata.create_all(self.engine)  # idempotent, rollback-safe

    def drop_all(self) -> None:
        _metadata.drop_all(self.engine)

    # -- coverage ---------------------------------------------------------
    def log_coverage(self, event: CoverageEvent) -> None:
        stmt = self._insert(extraction_coverage).values(
            doc_id=event.doc_id,
            chunk_id=event.chunk_id,
            extractor=event.extractor,
            target_type=event.target_type,
            attempted=event.attempted,
            found_count=event.found_count,
            run_id=event.run_id,
        )
        # on repeat: latest attempt wins (found_count/run_id refreshed), no dup row
        stmt = stmt.on_conflict_do_update(
            index_elements=["doc_id", "chunk_id", "extractor", "target_type"],
            set_={
                "attempted": stmt.excluded.attempted,
                "found_count": stmt.excluded.found_count,
                "run_id": stmt.excluded.run_id,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def coverage_stats(
        self, *, target_type: str | None = None, doc_id: str | None = None
    ) -> list[CoverageStats]:
        t = extraction_coverage
        # CASE (not CAST) so it is portable: Postgres rejects CAST(boolean AS int).
        attempted_int = case((t.c.attempted, 1), else_=0)
        found_int = case((t.c.found_count > 0, 1), else_=0)
        q = select(
            t.c.target_type,
            func.count().label("n_chunks"),
            func.sum(attempted_int).label("n_attempts"),
            func.sum(found_int).label("n_found"),
            func.count(func.distinct(t.c.doc_id)).label("n_docs"),
        ).group_by(t.c.target_type)
        if target_type is not None:
            q = q.where(t.c.target_type == target_type)
        if doc_id is not None:
            q = q.where(t.c.doc_id == doc_id)
        q = q.order_by(t.c.target_type)
        with self.engine.begin() as conn:
            rows = conn.execute(q).all()
        return [
            CoverageStats(
                target_type=r.target_type,
                n_chunks=int(r.n_chunks or 0),
                n_attempts=int(r.n_attempts or 0),
                n_found=int(r.n_found or 0),
                n_docs=int(r.n_docs or 0),
            )
            for r in rows
        ]

    # -- recall priors ----------------------------------------------------
    def save_recall_prior(self, prior: RecallPrior) -> None:
        stmt = self._insert(extractor_recall).values(
            extractor=prior.extractor,
            target_type=prior.target_type,
            recall=prior.recall,
            sample_size=prior.sample_size,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["extractor", "target_type"],
            set_={"recall": stmt.excluded.recall, "sample_size": stmt.excluded.sample_size},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_recall_priors(
        self, *, extractor: str | None = None, target_type: str | None = None
    ) -> list[RecallPrior]:
        t = extractor_recall
        q = select(t.c.extractor, t.c.target_type, t.c.recall, t.c.sample_size)
        if extractor is not None:
            q = q.where(t.c.extractor == extractor)
        if target_type is not None:
            q = q.where(t.c.target_type == target_type)
        q = q.order_by(t.c.extractor, t.c.target_type)
        with self.engine.begin() as conn:
            rows = conn.execute(q).all()
        return [
            RecallPrior(
                extractor=r.extractor,
                target_type=r.target_type,
                recall=float(r.recall),
                sample_size=int(r.sample_size),
            )
            for r in rows
        ]
