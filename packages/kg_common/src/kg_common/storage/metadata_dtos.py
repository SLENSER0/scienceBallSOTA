"""Metadata DTOs + register helpers over the catalog store (§9.2/§10.4).

Typed, frozen DTOs for the three catalog entities the §9.2 metadata model names —
*источник* (:class:`SourceMetadata`), *документ* (:class:`DocumentMetadata`) and
*датасет* (:class:`DatasetMetadata`) — plus ``register_source`` /
``register_document`` / ``register_dataset_meta`` that persist them idempotently
(§10.4 «повторный ingest ... обновляет, а не дублирует запись»).

This module builds **on** :mod:`kg_common.storage.metadata_catalog` by
composition: it reuses that catalog's shared engine and dialect-native
``INSERT ... ON CONFLICT DO UPDATE`` (``catalog._insert``, from
:func:`kg_common.storage.sql._dialect_insert`) and adds three small companion
tables on the same shared ``MetaData`` — the richer DTO shape (owner/lab/
access_policy/version/checksum …) does not fit the catalog's flat ``datasets``
row, so a dedicated table per entity keeps every field a first-class,
round-trippable column. No existing module is modified.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Table,
    select,
)

from kg_common.storage.sql import _metadata

if TYPE_CHECKING:  # avoid a hard runtime dep; composition is by duck-typing
    from kg_common.storage.metadata_catalog import MetadataCatalog

# -- companion schema (§10.4 register sources/documents/datasets) ---------
# Real SQL columns (SQLite embedded / Postgres server): unlike Kuzu custom node
# props these are all queryable, so read-back re-hydrates the DTO directly.
source_metadata = Table(
    "source_metadata",
    _metadata,
    Column("source_id", String, primary_key=True),
    Column("name", String, nullable=False, default=""),
    Column("owner", String, nullable=False, default=""),
    Column("lab", String, nullable=False, default=""),
    Column("access_policy", String, nullable=False, default="private"),
    Column("version", Integer, nullable=False, default=1),
    Column("ingestion_job_id", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
)

document_metadata = Table(
    "document_metadata",
    _metadata,
    Column("doc_id", String, primary_key=True),
    Column("source_id", String, nullable=False, default=""),
    Column("title", String, nullable=False, default=""),
    Column("media_type", String, nullable=False, default=""),
    Column("n_pages", Integer, nullable=False, default=0),
    Column("checksum", String, nullable=False, default=""),
)

dataset_metadata = Table(
    "dataset_metadata",
    _metadata,
    Column("dataset_id", String, primary_key=True),
    Column("doc_id", String, nullable=False, default=""),
    Column("kind", String, nullable=False, default="table"),
    Column("row_count", Integer, nullable=False, default=0),
)


def _require(data: Mapping[str, Any], key: str) -> Any:
    """Return ``data[key]`` or raise a clear ``KeyError`` — обязательное поле."""
    if key not in data:
        raise KeyError(f"required field missing: {key!r}")  # обязательное поле
    return data[key]


@dataclass(frozen=True)
class SourceMetadata:
    """A registered ingest *источник* — owner/lab/access/version (§9.2)."""

    source_id: str
    name: str = ""
    owner: str = ""
    lab: str = ""
    access_policy: str = "private"
    version: int = 1
    ingestion_job_id: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceMetadata:
        return cls(
            source_id=str(_require(data, "source_id")),
            name=str(data.get("name", "")),
            owner=str(data.get("owner", "")),
            lab=str(data.get("lab", "")),
            access_policy=str(data.get("access_policy", "private")),
            version=int(data.get("version", 1)),
            ingestion_job_id=str(data.get("ingestion_job_id", "")),
            created_at=str(data.get("created_at", "")),
        )


@dataclass(frozen=True)
class DocumentMetadata:
    """A *документ* under a source — media/pages/checksum (§9.2)."""

    doc_id: str
    source_id: str = ""
    title: str = ""
    media_type: str = ""
    n_pages: int = 0
    checksum: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DocumentMetadata:
        return cls(
            doc_id=str(_require(data, "doc_id")),
            source_id=str(data.get("source_id", "")),
            title=str(data.get("title", "")),
            media_type=str(data.get("media_type", "")),
            n_pages=int(data.get("n_pages", 0)),
            checksum=str(data.get("checksum", "")),
        )


@dataclass(frozen=True)
class DatasetMetadata:
    """A tabular/structured *датасет* extracted from a document (§9.2)."""

    dataset_id: str
    doc_id: str = ""
    kind: str = "table"
    row_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetMetadata:
        return cls(
            dataset_id=str(_require(data, "dataset_id")),
            doc_id=str(data.get("doc_id", "")),
            kind=str(data.get("kind", "table")),
            row_count=int(data.get("row_count", 0)),
        )


def next_version(meta: SourceMetadata) -> SourceMetadata:
    """Return a copy of ``meta`` with ``version`` bumped by one (§10.4 re-ingest)."""
    return dataclasses.replace(meta, version=meta.version + 1)


# create_all is cached per engine so each register() stays a single UPSERT.
_ENSURED: set[int] = set()


def ensure_schema(catalog: MetadataCatalog) -> None:
    """Idempotently create the companion tables on the catalog's engine."""
    key = id(catalog.engine)
    if key in _ENSURED:
        return
    _metadata.create_all(catalog.engine)  # idempotent, checkfirst, rollback-safe
    _ENSURED.add(key)


# -- register (idempotent UPSERT by primary key) --------------------------
def register_source(catalog: MetadataCatalog, meta: SourceMetadata) -> None:
    """UPSERT a source by ``source_id`` — re-register updates, never duplicates."""
    ensure_schema(catalog)
    stmt = catalog._insert(source_metadata).values(**meta.as_dict())
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_id"],
        set_={
            "name": stmt.excluded.name,
            "owner": stmt.excluded.owner,
            "lab": stmt.excluded.lab,
            "access_policy": stmt.excluded.access_policy,
            "version": stmt.excluded.version,
            "ingestion_job_id": stmt.excluded.ingestion_job_id,
            "created_at": stmt.excluded.created_at,
        },
    )
    with catalog.engine.begin() as conn:
        conn.execute(stmt)


def get_source(catalog: MetadataCatalog, source_id: str) -> SourceMetadata | None:
    """Read a source back, or ``None`` if unknown (§10.4)."""
    ensure_schema(catalog)
    t = source_metadata
    with catalog.engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.source_id == source_id)).first()
    return SourceMetadata(**row._mapping) if row else None


def list_sources(catalog: MetadataCatalog) -> list[SourceMetadata]:
    """All sources ordered by ``source_id`` (used to assert no duplicate rows)."""
    ensure_schema(catalog)
    t = source_metadata
    with catalog.engine.begin() as conn:
        rows = conn.execute(select(t).order_by(t.c.source_id)).all()
    return [SourceMetadata(**r._mapping) for r in rows]


def register_document(catalog: MetadataCatalog, meta: DocumentMetadata) -> None:
    """UPSERT a document by ``doc_id``; ``source_id`` links it to its source."""
    ensure_schema(catalog)
    stmt = catalog._insert(document_metadata).values(**meta.as_dict())
    stmt = stmt.on_conflict_do_update(
        index_elements=["doc_id"],
        set_={
            "source_id": stmt.excluded.source_id,
            "title": stmt.excluded.title,
            "media_type": stmt.excluded.media_type,
            "n_pages": stmt.excluded.n_pages,
            "checksum": stmt.excluded.checksum,
        },
    )
    with catalog.engine.begin() as conn:
        conn.execute(stmt)


def get_document(catalog: MetadataCatalog, doc_id: str) -> DocumentMetadata | None:
    """Read a document back, or ``None`` if unknown (§10.4)."""
    ensure_schema(catalog)
    t = document_metadata
    with catalog.engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.doc_id == doc_id)).first()
    return DocumentMetadata(**row._mapping) if row else None


def list_documents(
    catalog: MetadataCatalog, *, source_id: str | None = None
) -> list[DocumentMetadata]:
    """Documents ordered by ``doc_id``, optionally filtered by ``source_id``."""
    ensure_schema(catalog)
    t = document_metadata
    q = select(t)
    if source_id is not None:
        q = q.where(t.c.source_id == source_id)
    q = q.order_by(t.c.doc_id)
    with catalog.engine.begin() as conn:
        return [DocumentMetadata(**r._mapping) for r in conn.execute(q).all()]


def register_dataset_meta(catalog: MetadataCatalog, meta: DatasetMetadata) -> None:
    """UPSERT a dataset by ``dataset_id``; ``doc_id`` links it to its document."""
    ensure_schema(catalog)
    stmt = catalog._insert(dataset_metadata).values(**meta.as_dict())
    stmt = stmt.on_conflict_do_update(
        index_elements=["dataset_id"],
        set_={
            "doc_id": stmt.excluded.doc_id,
            "kind": stmt.excluded.kind,
            "row_count": stmt.excluded.row_count,
        },
    )
    with catalog.engine.begin() as conn:
        conn.execute(stmt)


def get_dataset_meta(catalog: MetadataCatalog, dataset_id: str) -> DatasetMetadata | None:
    """Read a dataset back, or ``None`` if unknown (§10.4)."""
    ensure_schema(catalog)
    t = dataset_metadata
    with catalog.engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.dataset_id == dataset_id)).first()
    return DatasetMetadata(**row._mapping) if row else None
