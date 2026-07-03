"""Ownership-coverage audit over the ownership store (§10.7).

Pure functions over an in-memory view of the ownership bindings (§10.6,
:mod:`kg_common.storage.ownership`) — no store, no I/O, no SQL, nothing is
written back. The caller materialises the bindings (e.g. via
``OwnershipStore.owners_of``) into a plain ``owners_map`` and asks: which catalog
assets have **no owner** at all? This powers the «missing metadata by lab/team» /
Gap Dashboard signal (§5.2.7): an unowned source/dataset (актив без владельца) is
a governance gap that must surface for triage.

Inputs (детерминированность — the audit reads only what you pass):

``assets``
    The catalog assets to audit (sources/documents/datasets, §10.4) as ids.
    Duplicate ids collapse to one (deduped).
``owners_map``
    ``{asset_id: [owner, ...]}`` — each owner is an owner-id ``str`` or an
    :class:`~kg_common.storage.ownership.Ownership` binding. An asset is *owned*
    when it maps to at least one owner; a missing or empty entry means *unowned*
    (актив без владельца). Entries for assets outside ``assets`` are ignored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from kg_common.storage.ownership import Ownership

_RATIO_PRECISION = 6  # округление доли покрытия (гасим шум float в отображении)


def _owner_id(owner: str | Ownership) -> str:
    """Owner id from a plain string or an :class:`Ownership` binding (§10.6)."""
    return owner.owner_id if isinstance(owner, Ownership) else str(owner)


@dataclass(frozen=True)
class OwnershipAudit:
    """Ownership-coverage snapshot — снимок покрытия владением (§10.7).

    Fields
    ------
    total:
        Assets audited (всего активов, deduped ``len(assets)``).
    owned:
        Assets with at least one owner (активы с владельцем).
    unowned:
        Sorted ids of assets with **no** owner (активы без владельца) — the gap
        the Gap Dashboard surfaces (§5.2.7).
    by_owner:
        ``{owner_id: count}`` — distinct assets each owner holds over the audited
        set (сколько активов у владельца), sorted by owner id.
    """

    total: int
    owned: int
    unowned: list[str] = field(default_factory=list)
    by_owner: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (JSON-friendly; ``unowned`` / ``by_owner`` copied)."""
        return asdict(self)


def audit_ownership(
    assets: Sequence[str],
    owners_map: Mapping[str, Sequence[str | Ownership]],
) -> OwnershipAudit:
    """Audit ownership coverage of ``assets`` against ``owners_map`` (§10.7).

    An asset is *owned* iff ``owners_map`` maps it to a non-empty owner list;
    otherwise it lands in ``unowned`` (актив без владельца). Duplicate asset ids
    collapse to one (deduped). ``by_owner`` counts *distinct* assets per owner over
    the audited set — an owner bound twice to one asset (two roles, §10.6) still
    counts once. See the module docstring for the input shapes.
    """
    seen: set[str] = set()
    unowned: list[str] = []
    by_owner: dict[str, int] = {}
    owned = 0
    for asset in assets:
        if asset in seen:
            continue  # дубликат актива не учитываем дважды
        seen.add(asset)
        owner_ids = {_owner_id(o) for o in owners_map.get(asset, ())}
        if owner_ids:
            owned += 1
            for oid in owner_ids:
                by_owner[oid] = by_owner.get(oid, 0) + 1
        else:
            unowned.append(asset)
    return OwnershipAudit(
        total=len(seen),
        owned=owned,
        unowned=sorted(unowned),
        by_owner=dict(sorted(by_owner.items())),
    )


def coverage_ratio(audit: OwnershipAudit) -> float:
    """Owned-asset fraction ``owned / total`` in ``[0.0, 1.0]`` (доля покрытия, §10.7).

    ``1.0`` when every audited asset has an owner, ``0.0`` for an empty audit (no
    assets → neither gap nor coverage). Rounded to keep the value hand-checkable.
    """
    if audit.total == 0:
        return 0.0
    return round(audit.owned / audit.total, _RATIO_PRECISION)
