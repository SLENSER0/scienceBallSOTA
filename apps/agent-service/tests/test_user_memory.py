"""§13.20 tests for long-term Store memory records / долговременная память Store.

Hand-checkable assertions covering :class:`MemoryRecord`, :func:`namespace`, and
:func:`prune` with no store or network involved.
"""

from __future__ import annotations

import pytest
from agent_service.user_memory import KINDS, MemoryRecord, namespace, prune


def _rec(key: str, created_at: float, ttl_s: float | None = None) -> MemoryRecord:
    """Build a valid ``canonical_entity`` record for tests."""
    return MemoryRecord(
        key=key,
        kind="canonical_entity",
        value={"name": key},
        created_at=created_at,
        ttl_s=ttl_s,
    )


def test_bogus_kind_raises() -> None:
    # (1) kind outside KINDS is rejected in __post_init__.
    with pytest.raises(ValueError):
        MemoryRecord(key="k", kind="bogus", value={}, created_at=0.0)


def test_all_kinds_construct() -> None:
    for kind in KINDS:
        rec = MemoryRecord(key="k", kind=kind, value={}, created_at=0.0)
        assert rec.kind == kind


def test_is_expired_ttl_and_none() -> None:
    # (2) created_at=0, ttl_s=10, now=100 → expired; ttl_s=None → never expired.
    expiring = _rec("a", created_at=0.0, ttl_s=10.0)
    assert expiring.is_expired(100.0) is True
    assert expiring.is_expired(5.0) is False
    # Boundary: now == created_at + ttl_s counts as expired.
    assert expiring.is_expired(10.0) is True
    never = _rec("b", created_at=0.0, ttl_s=None)
    assert never.is_expired(1_000_000.0) is False


def test_namespace() -> None:
    # (3) namespace is (user_id, "memories").
    assert namespace("u1") == ("u1", "memories")


def test_prune_removes_expired() -> None:
    # (4) an expired record is dropped by prune.
    fresh = _rec("fresh", created_at=50.0, ttl_s=None)
    stale = _rec("stale", created_at=0.0, ttl_s=10.0)
    kept = prune([fresh, stale], now=100.0, max_items=10)
    assert kept == [fresh]


def test_prune_caps_to_max_items_keeping_newest() -> None:
    # (5) prune keeps the newest max_items by created_at.
    r_old = _rec("old", created_at=1.0)
    r_mid = _rec("mid", created_at=2.0)
    r_new = _rec("new", created_at=3.0)
    kept = prune([r_old, r_new, r_mid], now=100.0, max_items=2)
    assert kept == [r_new, r_mid]


def test_as_dict_round_trips_value() -> None:
    # (6) as_dict preserves the value dict and all fields.
    value = {"canonical": "Aspirin", "aliases": ["ASA"]}
    rec = MemoryRecord(
        key="drug:aspirin",
        kind="canonical_entity",
        value=value,
        created_at=12.5,
        ttl_s=None,
    )
    d = rec.as_dict()
    assert d == {
        "key": "drug:aspirin",
        "kind": "canonical_entity",
        "value": value,
        "created_at": 12.5,
        "ttl_s": None,
    }
    assert d["value"] == value


def test_prune_all_fresh_fewer_than_max_returns_all() -> None:
    # (7) all fresh + fewer than max_items → all survivors, newest→oldest.
    r1 = _rec("r1", created_at=1.0)
    r2 = _rec("r2", created_at=2.0)
    kept = prune([r1, r2], now=100.0, max_items=10)
    assert kept == [r2, r1]


def test_prune_non_positive_max_items() -> None:
    assert prune([_rec("x", created_at=1.0)], now=0.0, max_items=0) == []
