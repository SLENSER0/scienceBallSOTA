"""Ownership-coverage audit over the ownership store (§10.7)."""

from __future__ import annotations

from kg_common.storage.ownership import Ownership
from kg_common.storage.ownership_audit import (
    OwnershipAudit,
    audit_ownership,
    coverage_ratio,
)

# Shared scenario: 4 assets, 2 owned (one by two owners), 2 unowned.
_ASSETS = ["src:1", "src:2", "src:3", "src:4"]
_OWNERS_MAP = {
    "src:1": ["lab:neuro"],
    "src:2": ["lab:neuro", "team:data"],
    "src:3": [],  # explicit empty → unowned
    # src:4 absent from the map → unowned
}


def test_unowned_listed() -> None:
    audit = audit_ownership(_ASSETS, _OWNERS_MAP)
    assert audit.unowned == ["src:3", "src:4"]  # sorted, both gaps present


def test_owned_count() -> None:
    audit = audit_ownership(_ASSETS, _OWNERS_MAP)
    assert audit.total == 4
    assert audit.owned == 2  # src:1, src:2


def test_by_owner_buckets() -> None:
    audit = audit_ownership(_ASSETS, _OWNERS_MAP)
    assert audit.by_owner == {"lab:neuro": 2, "team:data": 1}


def test_coverage_ratio() -> None:
    audit = audit_ownership(_ASSETS, _OWNERS_MAP)
    assert coverage_ratio(audit) == 0.5  # 2 owned / 4 total


def test_all_owned_ratio_one() -> None:
    audit = audit_ownership(["a", "b"], {"a": ["o1"], "b": ["o2"]})
    assert audit.unowned == []
    assert coverage_ratio(audit) == 1.0


def test_empty_zeros() -> None:
    audit = audit_ownership([], {})
    assert audit.total == 0
    assert audit.owned == 0
    assert audit.unowned == []
    assert audit.by_owner == {}
    assert coverage_ratio(audit) == 0.0


def test_as_dict() -> None:
    audit = audit_ownership(_ASSETS, _OWNERS_MAP)
    assert audit.as_dict() == {
        "total": 4,
        "owned": 2,
        "unowned": ["src:3", "src:4"],
        "by_owner": {"lab:neuro": 2, "team:data": 1},
    }


def test_ownership_objects_extract_owner_id() -> None:
    owners_map = {"src:1": [Ownership("src:1", "lab:neuro", role="owner")]}
    audit = audit_ownership(["src:1"], owners_map)
    assert audit.owned == 1
    assert audit.by_owner == {"lab:neuro": 1}


def test_same_owner_two_roles_counts_once() -> None:
    owners_map = {
        "src:1": [
            Ownership("src:1", "lab:neuro", role="owner"),
            Ownership("src:1", "lab:neuro", role="technical_owner"),
        ]
    }
    audit = audit_ownership(["src:1"], owners_map)
    assert audit.owned == 1
    assert audit.by_owner == {"lab:neuro": 1}  # deduped per asset


def test_duplicate_assets_deduped() -> None:
    audit = audit_ownership(["src:1", "src:1"], {"src:1": ["o"]})
    assert audit.total == 1
    assert audit.owned == 1
    assert audit.by_owner == {"o": 1}


def test_as_dict_returns_copies() -> None:
    audit = audit_ownership(_ASSETS, _OWNERS_MAP)
    dumped = audit.as_dict()
    dumped["unowned"].append("mutated")
    dumped["by_owner"]["lab:neuro"] = 99
    assert audit.unowned == ["src:3", "src:4"]  # source untouched
    assert audit.by_owner == {"lab:neuro": 2, "team:data": 1}


def test_frozen_dataclass_immutable() -> None:
    audit = OwnershipAudit(total=1, owned=1)
    try:
        audit.total = 2  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("OwnershipAudit must be frozen")
