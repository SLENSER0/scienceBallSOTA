"""Source ownership → lab/team binding (§10.6)."""

from __future__ import annotations

import pytest

from kg_common.storage.ownership import Ownership, OwnershipStore


@pytest.fixture
def store() -> OwnershipStore:
    s = OwnershipStore("sqlite:///:memory:")
    s.migrate()
    return s


def test_assign_and_owners_of(store: OwnershipStore) -> None:
    store.assign_owner("src:1", "lab:neuro", owner_type="lab", role="owner")
    owners = store.owners_of("src:1")
    assert len(owners) == 1
    o = owners[0]
    assert o.asset_id == "src:1" and o.owner_id == "lab:neuro"
    assert o.owner_type == "lab" and o.role == "owner"


def test_assign_defaults(store: OwnershipStore) -> None:
    store.assign_owner("src:2", "team:alpha")  # owner_type/role defaults
    o = store.owners_of("src:2")[0]
    assert o.owner_type == "lab" and o.role == "owner"


def test_reassign_is_idempotent_upsert(store: OwnershipStore) -> None:
    store.assign_owner("src:1", "lab:neuro", owner_type="lab", role="owner")
    store.assign_owner("src:1", "lab:neuro", owner_type="team", role="owner")  # update
    owners = store.owners_of("src:1")
    assert len(owners) == 1  # no duplicate row
    assert owners[0].owner_type == "team"  # owner_type refreshed


def test_assets_of_reverse_lookup(store: OwnershipStore) -> None:
    store.assign_owner("src:1", "lab:neuro")
    store.assign_owner("src:2", "lab:neuro")
    store.assign_owner("src:3", "lab:other")
    assets = store.assets_of("lab:neuro")
    assert [a.asset_id for a in assets] == ["src:1", "src:2"]
    assert store.assets_of("lab:other")[0].asset_id == "src:3"


def test_multiple_owners_per_asset_with_roles(store: OwnershipStore) -> None:
    store.assign_owner("src:1", "lab:neuro", owner_type="lab", role="owner")
    store.assign_owner("src:1", "person:ivanov", owner_type="person", role="technical_owner")
    store.assign_owner("src:1", "team:data", owner_type="team", role="data_owner")
    owners = store.owners_of("src:1")
    assert len(owners) == 3
    roles = {o.role for o in owners}
    assert roles == {"owner", "technical_owner", "data_owner"}


def test_same_owner_two_roles_are_distinct(store: OwnershipStore) -> None:
    store.assign_owner("src:1", "lab:neuro", role="owner")
    store.assign_owner("src:1", "lab:neuro", role="technical_owner")
    assert len(store.owners_of("src:1")) == 2  # UNIQUE(asset, owner, role)


def test_remove_owner(store: OwnershipStore) -> None:
    store.assign_owner("src:1", "lab:neuro", role="owner")
    store.assign_owner("src:1", "person:ivanov", role="technical_owner")
    store.remove_owner("src:1", "lab:neuro", role="owner")
    remaining = store.owners_of("src:1")
    assert len(remaining) == 1 and remaining[0].owner_id == "person:ivanov"


def test_empty_and_graceful_remove(store: OwnershipStore) -> None:
    assert store.owners_of("missing") == []
    assert store.assets_of("missing") == []
    store.remove_owner("missing", "nobody")  # no-op, must not raise


def test_ownership_as_dict() -> None:
    o = Ownership("src:1", "lab:neuro", owner_type="lab", role="owner")
    assert o.as_dict() == {
        "asset_id": "src:1",
        "owner_id": "lab:neuro",
        "owner_type": "lab",
        "role": "owner",
    }
