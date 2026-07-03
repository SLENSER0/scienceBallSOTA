"""Tests for ownership transfer on merge/split/alias (§10.6).

Hand-checkable: merging m1(owners=['u1']) into s(owners=['u2']) transfers u1 onto s; owners
already on the survivor produce no transfer; output is deterministically sorted.
"""

from __future__ import annotations

from kg_common.metadata.ownership_transfer import (
    OwnershipTransfer,
    merged_owner_union,
    transfer_on_merge,
)


def test_merge_transfers_owner_to_survivor() -> None:
    owners = {"s": ["u2"], "m1": ["u1"]}
    result = transfer_on_merge("s", ["m1"], owners)
    assert len(result) == 1
    t = result[0]
    assert t.to_owner == "s"
    assert t.from_owner == "u1"
    assert t.asset_id == "s"


def test_transfer_reason_is_merge() -> None:
    owners = {"s": ["u2"], "m1": ["u1"]}
    result = transfer_on_merge("s", ["m1"], owners)
    assert result[0].reason == "merge"


def test_owner_already_on_survivor_produces_no_transfer() -> None:
    # u2 is an owner of both s and m1 → already preserved, nothing to transfer.
    owners = {"s": ["u2"], "m1": ["u2"]}
    assert transfer_on_merge("s", ["m1"], owners) == []


def test_output_sorted_by_asset_and_from_owner() -> None:
    # Multiple merged assets with owners in non-sorted order → result sorted deterministically.
    owners = {"s": [], "m1": ["u3", "u1"], "m2": ["u2"]}
    result = transfer_on_merge("s", ["m2", "m1"], owners)
    from_owners = [t.from_owner for t in result]
    assert from_owners == ["u1", "u2", "u3"]
    assert result == sorted(result, key=lambda t: (t.asset_id, t.from_owner))
    assert all(t.to_owner == "s" and t.asset_id == "s" for t in result)


def test_owner_on_two_merged_assets_transferred_once() -> None:
    owners = {"s": [], "m1": ["u1"], "m2": ["u1"]}
    result = transfer_on_merge("s", ["m1", "m2"], owners)
    assert [t.from_owner for t in result] == ["u1"]


def test_empty_merge_yields_empty() -> None:
    assert transfer_on_merge("s", [], {}) == []


def test_role_default_owner_preserved_and_overridable() -> None:
    owners = {"s": ["u2"], "m1": ["u1"]}
    default = transfer_on_merge("s", ["m1"], owners)
    assert default[0].role == "owner"
    custom = transfer_on_merge("s", ["m1"], owners, role="technical_owner")
    assert custom[0].role == "technical_owner"


def test_merged_owner_union_sorted() -> None:
    assert merged_owner_union("s", ["m1"], {"s": ["u2"], "m1": ["u1"]}) == ("u1", "u2")


def test_merged_owner_union_dedups_and_sorts() -> None:
    owners = {"s": ["u2", "u3"], "m1": ["u1", "u2"], "m2": ["u3"]}
    assert merged_owner_union("s", ["m1", "m2"], owners) == ("u1", "u2", "u3")


def test_as_dict_round_trip() -> None:
    t = OwnershipTransfer(
        asset_id="s",
        from_owner="u1",
        to_owner="s",
        role="owner",
        reason="merge",
    )
    d = t.as_dict()
    assert d["to_owner"] == "s"
    assert d == {
        "asset_id": "s",
        "from_owner": "u1",
        "to_owner": "s",
        "role": "owner",
        "reason": "merge",
    }


def test_missing_survivor_owners_treated_as_empty() -> None:
    # survivor_id absent from mapping → no existing owners, merged owner transfers.
    result = transfer_on_merge("s", ["m1"], {"m1": ["u1"]})
    assert [t.from_owner for t in result] == ["u1"]
