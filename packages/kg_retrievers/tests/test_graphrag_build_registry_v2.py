"""Tests for the GraphRAG build registry (§11.10).

Тесты реестра сборок — every expected value below is hand-checkable from the
register/activate/rollback/prune semantics: activation is exclusive, rollback
steps back to the previous ``built`` version, and prune drops the oldest
non-active builds while sparing the active one.
"""

from __future__ import annotations

import pytest

from kg_retrievers.graphrag_build_registry_v2 import BuildRecord, BuildRegistry


def _built_registry() -> BuildRegistry:
    """RU: Реестр с двумя built-сборками. EN: Registry with two built builds."""
    reg = BuildRegistry()
    reg.register("v1", n_communities=10, created_at="2026-07-01T00:00:00Z")
    reg.register("v2", n_communities=12, created_at="2026-07-02T00:00:00Z")
    return reg


def test_activate_second_makes_it_active_and_unique() -> None:
    """Activating v2 -> active_version is v2 and exactly one record active."""
    reg = _built_registry()
    reg.activate("v2")
    assert reg.active_version() == "v2"
    actives = [r for r in reg.as_dict()["records"] if r["active"]]
    assert len(actives) == 1
    assert actives[0]["build_version"] == "v2"


def test_activate_failed_build_raises() -> None:
    """Activating a status='failed' build raises ValueError."""
    reg = BuildRegistry()
    reg.register("v1", n_communities=0, created_at="2026-07-01T00:00:00Z", status="failed")
    with pytest.raises(ValueError):
        reg.activate("v1")
    assert reg.active_version() is None


def test_rollback_reactivates_prior_version() -> None:
    """After activating newer v2, rollback returns 'v1' and re-activates it."""
    reg = _built_registry()
    reg.activate("v1")
    reg.activate("v2")
    assert reg.active_version() == "v2"
    rolled = reg.rollback()
    assert rolled == "v1"
    assert reg.active_version() == "v1"


def test_prune_keep_one_drops_two_oldest_non_active() -> None:
    """prune(keep=1) over 3 builds drops the 2 oldest, keeps the active one."""
    reg = BuildRegistry()
    reg.register("v1", n_communities=1, created_at="2026-07-01T00:00:00Z")
    reg.register("v2", n_communities=2, created_at="2026-07-02T00:00:00Z")
    reg.register("v3", n_communities=3, created_at="2026-07-03T00:00:00Z")
    reg.activate("v3")
    removed = reg.prune(keep=1)
    assert removed == ["v1", "v2"]
    remaining = [r["build_version"] for r in reg.as_dict()["records"]]
    assert remaining == ["v3"]
    assert reg.active_version() == "v3"


def test_active_version_none_before_activation() -> None:
    """active_version() is None before any activation."""
    reg = _built_registry()
    assert reg.active_version() is None


def test_prune_removed_matches_deleted_versions() -> None:
    """Removed list exactly equals the versions no longer present."""
    reg = BuildRegistry()
    for i in range(1, 5):
        reg.register(f"v{i}", n_communities=i, created_at=f"2026-07-0{i}T00:00:00Z")
    reg.activate("v2")
    before = {r["build_version"] for r in reg.as_dict()["records"]}
    removed = reg.prune(keep=1)
    after = {r["build_version"] for r in reg.as_dict()["records"]}
    assert set(removed) == before - after
    # keep=1 but active v2 is spared, so it plus nothing else remains.
    assert after == {"v2"}
    assert removed == ["v1", "v3", "v4"]


def test_as_dict_has_exactly_one_active_after_activate() -> None:
    """as_dict has exactly one record with active=True after activate."""
    reg = _built_registry()
    reg.activate("v1")
    records = reg.as_dict()["records"]
    active_flags = [r["active"] for r in records]
    assert active_flags.count(True) == 1
    first = records[0]
    assert isinstance(BuildRecord(**{k: first[k] for k in first}), BuildRecord)
