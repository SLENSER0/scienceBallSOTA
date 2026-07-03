"""Source registry (§5.4): registered ingest sources + provenance/license.

Tracks every document/source the system ingested — uri, title, doc_type, license,
content hash, status, timestamps — so re-ingestion is deduped by content hash and
license/provenance is auditable. Same backend-agnostic SQLAlchemy design as the
MetaStore (SQLite embedded / Postgres server), idempotent UPSERT by source_id.
"""

from __future__ import annotations

from dataclasses import dataclass

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

sources = Table(
    "ingest_sources",
    _metadata,
    Column("source_id", String, primary_key=True),
    Column("uri", String, nullable=False, default=""),
    Column("title", String, nullable=False, default=""),
    Column("doc_type", String, nullable=False, default="unknown"),
    Column("license", String, nullable=False, default="unknown"),
    Column("sha256", String, nullable=False, default=""),
    Column("country", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="registered"),
    Column("n_chunks", Integer, nullable=False, default=0),
    UniqueConstraint("sha256", name="uq_source_sha"),
)


@dataclass(frozen=True)
class Source:
    source_id: str
    uri: str = ""
    title: str = ""
    doc_type: str = "unknown"
    license: str = "unknown"
    sha256: str = ""
    country: str = ""
    status: str = "registered"
    n_chunks: int = 0


class SourceRegistry:
    """Concrete registry over any SQLAlchemy URL (SQLite embedded / Postgres server)."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    def migrate(self) -> None:
        _metadata.create_all(self.engine)

    def register(self, src: Source) -> None:
        stmt = self._insert(sources).values(
            source_id=src.source_id,
            uri=src.uri,
            title=src.title,
            doc_type=src.doc_type,
            license=src.license,
            sha256=src.sha256,
            country=src.country,
            status=src.status,
            n_chunks=src.n_chunks,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id"],
            set_={
                "uri": stmt.excluded.uri,
                "title": stmt.excluded.title,
                "doc_type": stmt.excluded.doc_type,
                "license": stmt.excluded.license,
                "sha256": stmt.excluded.sha256,
                "country": stmt.excluded.country,
                "status": stmt.excluded.status,
                "n_chunks": stmt.excluded.n_chunks,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get(self, source_id: str) -> Source | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(sources).where(sources.c.source_id == source_id)).first()
        return Source(**row._mapping) if row else None

    def by_hash(self, sha256: str) -> Source | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(sources).where(sources.c.sha256 == sha256)).first()
        return Source(**row._mapping) if row else None

    def exists(self, sha256: str) -> bool:
        return self.by_hash(sha256) is not None

    def list(self, *, doc_type: str | None = None) -> list[Source]:
        q = select(sources)
        if doc_type is not None:
            q = q.where(sources.c.doc_type == doc_type)
        q = q.order_by(sources.c.source_id)
        with self.engine.begin() as conn:
            return [Source(**r._mapping) for r in conn.execute(q).all()]

    def counts_by_license(self) -> dict[str, int]:
        q = select(sources.c.license, func.count()).group_by(sources.c.license)
        with self.engine.begin() as conn:
            return dict(conn.execute(q).all())
