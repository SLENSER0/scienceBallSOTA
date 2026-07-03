"""Source ownership → lab/team binding (§10.6).

Binds catalog assets (sources/documents/datasets, §10.4) to their owners —
labs, teams or people (`Lab`/`ResearchTeam`/`Person`, core labels §8.1) — with a
role (owner / technical_owner / data_owner, mapping the catalog ownership-aspect
`DATAOWNER`/`TECHNICAL_OWNER` of §10.6). An asset may have several owners with
distinct roles (владелец / технический владелец), and an owner (лаборатория /
команда) may own many assets. This is the source of truth consumed by the
ownership-audit «missing metadata by lab/team» (§10.6 / Gap Dashboard §5.2.7).

Same backend-agnostic SQLAlchemy design as the MetaStore (SQLite embedded /
Postgres server): reuses ``SqlMetaStore`` engine + shared ``_metadata`` +
``_dialect_insert``. ``assign_owner`` is an idempotent UPSERT keyed on
``(asset_id, owner_id, role)`` so re-binding the same owner never duplicates.
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

ownership = Table(
    "ownership",
    _metadata,
    Column("asset_id", String, nullable=False),
    Column("owner_id", String, nullable=False),
    Column("owner_type", String, nullable=False, default="lab"),
    Column("role", String, nullable=False, default="owner"),
    # владелец роли для актива уникален: (asset, owner, role) не дублируется
    UniqueConstraint("asset_id", "owner_id", "role", name="uq_ownership_key"),
)


@dataclass(frozen=True)
class Ownership:
    """A single owner→asset binding (§10.6): who owns what, in which role.

    RU/EN: ``owner_type`` — тип владельца (lab/team/person); ``role`` — роль
    (owner / technical_owner / data_owner).
    """

    asset_id: str
    owner_id: str
    owner_type: str = "lab"
    role: str = "owner"

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (для сериализации в каталог/audit §10.6)."""
        return asdict(self)


class OwnershipStore:
    """Ownership bindings over any SQLAlchemy URL (SQLite embedded / Postgres server).

    Reuses the :class:`~kg_common.storage.sql.SqlMetaStore` engine and the shared
    ``_metadata`` so ownership lives alongside sources/coverage in one store (§10.6).
    """

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    def migrate(self) -> None:
        """Create the ``ownership`` table (idempotent, §10.6)."""
        _metadata.create_all(self.engine)

    def assign_owner(
        self,
        asset_id: str,
        owner_id: str,
        owner_type: str = "lab",
        role: str = "owner",
    ) -> None:
        """Bind ``owner_id`` to ``asset_id`` in ``role`` (idempotent UPSERT, §10.6).

        Re-assigning the same ``(asset_id, owner_id, role)`` refreshes ``owner_type``
        instead of inserting a duplicate row (повторная привязка идемпотентна).
        """
        stmt = self._insert(ownership).values(
            asset_id=asset_id,
            owner_id=owner_id,
            owner_type=owner_type,
            role=role,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["asset_id", "owner_id", "role"],
            set_={"owner_type": stmt.excluded.owner_type},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def owners_of(self, asset_id: str) -> list[Ownership]:
        """List owners bound to ``asset_id`` (владельцы актива, §10.6)."""
        q = (
            select(ownership)
            .where(ownership.c.asset_id == asset_id)
            .order_by(ownership.c.owner_id, ownership.c.role)
        )
        with self.engine.begin() as conn:
            return [Ownership(**r._mapping) for r in conn.execute(q).all()]

    def assets_of(self, owner_id: str) -> list[Ownership]:
        """Reverse lookup: assets owned by ``owner_id`` (активы владельца, §10.6)."""
        q = (
            select(ownership)
            .where(ownership.c.owner_id == owner_id)
            .order_by(ownership.c.asset_id, ownership.c.role)
        )
        with self.engine.begin() as conn:
            return [Ownership(**r._mapping) for r in conn.execute(q).all()]

    def remove_owner(self, asset_id: str, owner_id: str, role: str = "owner") -> None:
        """Unbind ``owner_id`` from ``asset_id`` in ``role`` (graceful no-op if absent)."""
        stmt = delete(ownership).where(
            and_(
                ownership.c.asset_id == asset_id,
                ownership.c.owner_id == owner_id,
                ownership.c.role == role,
            )
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
