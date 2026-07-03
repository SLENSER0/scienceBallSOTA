"""Metadata/lineage catalog store (§10.3/§10.4/§10.5).

Embedded SQLite / server Postgres catalog of *datasets* (реестр датасетов
каталога: источники, документы, Neo4j/Qdrant/OpenSearch артефакты — §10.4) and
pipeline-run *lineage* (граф происхождения inputs→outputs каждого прогона —
§10.5). Same backend-agnostic SQLAlchemy design as
:class:`~kg_common.storage.sql.SqlMetaStore` and
:class:`~kg_common.storage.source_registry.SourceRegistry`: it reuses the shared
engine + ``MetaData`` and the dialect-native ``INSERT ... ON CONFLICT DO
UPDATE`` (SQLite ≥3.24 and Postgres) so re-registering a dataset or re-emitting
a lineage edge is idempotent (§10.4 «повторный ingest ... обновляет, а не
дублирует запись»).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Table,
    UniqueConstraint,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# -- schema (§10.3 model of metadata) -------------------------------------
datasets = Table(
    "datasets",
    _metadata,
    Column("dataset_id", String, primary_key=True),
    Column("name", String, nullable=False, default=""),
    Column("kind", String, nullable=False, default="dataset"),
    Column("uri", String, nullable=False, default=""),
    Column("n_records", Integer, nullable=False, default=0),
    Column("owner", String, nullable=False, default=""),
)

lineage = Table(
    "lineage",
    _metadata,
    Column("run_id", String, nullable=False),
    Column("asset", String, nullable=False),
    Column("upstream", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="success"),
    Column("started_at", String, nullable=False, default=""),
    Column("kind", String, nullable=False, default="asset"),
    # one directed edge (upstream → asset) per run; re-emit updates, never dups
    UniqueConstraint("run_id", "asset", "upstream", name="uq_lineage_edge"),
)


@dataclass(frozen=True)
class Dataset:
    """A catalog dataset — источник/документ/индекс/граф (§10.4)."""

    dataset_id: str
    name: str = ""
    kind: str = "dataset"
    uri: str = ""
    n_records: int = 0
    owner: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LineageEdge:
    """One inputs→output edge of a pipeline run (§10.5).

    Flow direction is ``upstream`` → ``asset``. ``upstream`` is empty for a root
    asset (RAW-источник без предков). ``kind`` classifies the produced asset
    (``source``/``document``/``chunks``/``triples``/``neo4j``/``qdrant`` …).
    """

    run_id: str
    asset: str
    upstream: str = ""
    status: str = "success"
    started_at: str = ""
    kind: str = "asset"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetadataCatalog:
    """Datasets + lineage catalog over any SQLAlchemy URL (§10.3/§10.4/§10.5).

    SQLite for the embedded profile, PostgreSQL for the server profile; identical
    SQL/UPSERT keys across both (parity with ``SqlMetaStore``/``SourceRegistry``).
    """

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    def migrate(self) -> None:
        _metadata.create_all(self.engine)  # idempotent, rollback-safe

    # -- datasets (§10.4 register datasets/documents/sources) -------------
    def register_dataset(self, ds: Dataset) -> None:
        """Idempotent UPSERT of a dataset by ``dataset_id`` (re-register updates)."""
        stmt = self._insert(datasets).values(
            dataset_id=ds.dataset_id,
            name=ds.name,
            kind=ds.kind,
            uri=ds.uri,
            n_records=ds.n_records,
            owner=ds.owner,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["dataset_id"],
            set_={
                "name": stmt.excluded.name,
                "kind": stmt.excluded.kind,
                "uri": stmt.excluded.uri,
                "n_records": stmt.excluded.n_records,
                "owner": stmt.excluded.owner,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(datasets).where(datasets.c.dataset_id == dataset_id)).first()
        return Dataset(**row._mapping) if row else None

    def list_datasets(self, *, kind: str | None = None, owner: str | None = None) -> list[Dataset]:
        q = select(datasets)
        if kind is not None:
            q = q.where(datasets.c.kind == kind)
        if owner is not None:
            q = q.where(datasets.c.owner == owner)
        q = q.order_by(datasets.c.dataset_id)
        with self.engine.begin() as conn:
            return [Dataset(**r._mapping) for r in conn.execute(q).all()]

    # -- lineage (§10.5 emit pipeline metadata + lineage) ----------------
    def record_lineage(self, edge: LineageEdge) -> None:
        """Idempotent UPSERT of one (run_id, asset, upstream) lineage edge."""
        stmt = self._insert(lineage).values(
            run_id=edge.run_id,
            asset=edge.asset,
            upstream=edge.upstream,
            status=edge.status,
            started_at=edge.started_at,
            kind=edge.kind,
        )
        # re-emit: latest status/timestamp/kind wins, edge is not duplicated
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id", "asset", "upstream"],
            set_={
                "status": stmt.excluded.status,
                "started_at": stmt.excluded.started_at,
                "kind": stmt.excluded.kind,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def lineage_for(self, asset: str) -> list[LineageEdge]:
        """Every edge touching ``asset`` — as produced output or as an upstream."""
        t = lineage
        q = (
            select(t)
            .where((t.c.asset == asset) | (t.c.upstream == asset))
            .order_by(t.c.run_id, t.c.asset, t.c.upstream)
        )
        with self.engine.begin() as conn:
            return [LineageEdge(**r._mapping) for r in conn.execute(q).all()]

    def upstreams_of(self, asset: str) -> list[str]:
        """Direct parents ``asset`` was produced from (empty upstreams excluded)."""
        t = lineage
        q = (
            select(t.c.upstream)
            .where(t.c.asset == asset, t.c.upstream != "")
            .distinct()
            .order_by(t.c.upstream)
        )
        with self.engine.begin() as conn:
            return [r.upstream for r in conn.execute(q).all()]

    def downstreams_of(self, asset: str) -> list[str]:
        """Direct children produced from ``asset``."""
        t = lineage
        q = select(t.c.asset).where(t.c.upstream == asset).distinct().order_by(t.c.asset)
        with self.engine.begin() as conn:
            return [r.asset for r in conn.execute(q).all()]

    def list_lineage(
        self,
        *,
        run_id: str | None = None,
        asset: str | None = None,
        status: str | None = None,
    ) -> list[LineageEdge]:
        t = lineage
        q = select(t)
        if run_id is not None:
            q = q.where(t.c.run_id == run_id)
        if asset is not None:
            q = q.where(t.c.asset == asset)
        if status is not None:
            q = q.where(t.c.status == status)
        q = q.order_by(t.c.run_id, t.c.asset, t.c.upstream)
        with self.engine.begin() as conn:
            return [LineageEdge(**r._mapping) for r in conn.execute(q).all()]
