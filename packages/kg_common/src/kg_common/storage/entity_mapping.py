"""Entity crosswalk → external-id to canonical-id mapping (§10.3).

Maps identifiers minted by external systems (ORCID, ROR, PubMed PMID, an internal
LIMS/lab id, …) onto the one *canonical* entity id used inside the knowledge graph,
so the same real-world entity ingested from several sources collapses to a single
node (перекрёстная сшивка идентификаторов). A given ``external_id`` is only unique
*within* its ``source_system`` — the same numeric string may be a PMID in one system
and a lab record id in another — hence the crosswalk is keyed on the pair
``(external_id, source_system)``, and many external ids (from many systems) may point
at one ``canonical_id``.

Same backend-agnostic SQLAlchemy design as the MetaStore (SQLite embedded / Postgres
server): reuses the :class:`~kg_common.storage.sql.SqlMetaStore` engine + shared
``_metadata`` + ``_dialect_insert``. ``map_id`` is an idempotent UPSERT keyed on
``(external_id, source_system)`` so re-mapping the same external id never duplicates —
it just re-points it at the (possibly new) canonical id (повторная сшивка идемпотентна).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import (
    Column,
    String,
    Table,
    UniqueConstraint,
    and_,
    delete,
    select,
)

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

entity_crosswalk = Table(
    "entity_crosswalk",
    _metadata,
    Column("external_id", String, nullable=False),
    Column("source_system", String, nullable=False),
    Column("canonical_id", String, nullable=False),
    # внешний id уникален лишь внутри своей системы-источника
    UniqueConstraint("external_id", "source_system", name="uq_crosswalk_key"),
)


@dataclass(frozen=True)
class Crosswalk:
    """A single external-id → canonical-id mapping (§10.3).

    RU/EN: ``source_system`` — система-источник внешнего id (ORCID/ROR/PMID/LIMS…);
    ``canonical_id`` — канонический id сущности в графе знаний.
    """

    external_id: str
    source_system: str
    canonical_id: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (для сериализации в каталог/резолвер §10.3)."""
        return asdict(self)


class EntityMapping:
    """Entity crosswalk over any SQLAlchemy URL (SQLite embedded / Postgres server).

    Reuses the :class:`~kg_common.storage.sql.SqlMetaStore` engine and the shared
    ``_metadata`` so the crosswalk lives alongside sources/ownership in one store (§10.3).
    """

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    def migrate(self) -> None:
        """Create the ``entity_crosswalk`` table (idempotent, §10.3)."""
        _metadata.create_all(self.engine)

    def map_id(self, external_id: str, source_system: str, canonical_id: str) -> None:
        """Map ``(external_id, source_system)`` → ``canonical_id`` (idempotent UPSERT, §10.3).

        Re-mapping the same ``(external_id, source_system)`` re-points it at the new
        ``canonical_id`` instead of inserting a duplicate row (повторная сшивка
        обновляет канонический id).
        """
        stmt = self._insert(entity_crosswalk).values(
            external_id=external_id,
            source_system=source_system,
            canonical_id=canonical_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_id", "source_system"],
            set_={"canonical_id": stmt.excluded.canonical_id},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def resolve(self, external_id: str, source_system: str) -> str | None:
        """Resolve ``(external_id, source_system)`` → ``canonical_id`` or ``None`` (§10.3)."""
        q = select(entity_crosswalk.c.canonical_id).where(
            and_(
                entity_crosswalk.c.external_id == external_id,
                entity_crosswalk.c.source_system == source_system,
            )
        )
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return row.canonical_id if row else None

    def external_ids_for(self, canonical_id: str) -> list[Crosswalk]:
        """Reverse lookup: all external ids mapped to ``canonical_id`` (§10.3).

        Returns the full crosswalk rows (система-источник + внешний id) so callers can
        tell apart the same external id string coming from different source systems.
        """
        q = (
            select(entity_crosswalk)
            .where(entity_crosswalk.c.canonical_id == canonical_id)
            .order_by(entity_crosswalk.c.source_system, entity_crosswalk.c.external_id)
        )
        with self.engine.begin() as conn:
            return [Crosswalk(**r._mapping) for r in conn.execute(q).all()]

    def remove(self, external_id: str, source_system: str) -> None:
        """Drop the ``(external_id, source_system)`` mapping (graceful no-op if absent, §10.3)."""
        stmt = delete(entity_crosswalk).where(
            and_(
                entity_crosswalk.c.external_id == external_id,
                entity_crosswalk.c.source_system == source_system,
            )
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
