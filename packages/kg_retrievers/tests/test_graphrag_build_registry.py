"""Tests for §11.10 GraphRAG build registry / Тесты реестра сборок GraphRAG."""

from __future__ import annotations

import pytest

from kg_retrievers.graphrag_build_registry import BuildRecord, BuildRegistry


def _registry_two_built() -> BuildRegistry:
    """Registry with two built versions v1, v2 / Реестр с v1, v2."""
    reg = BuildRegistry()
    reg.register("v1", n_communities=10, created_at="2026-01-01T00:00:00Z")
    reg.register("v2", n_communities=12, created_at="2026-02-01T00:00:00Z")
    return reg


def test_register_and_activate_v1_single_active() -> None:
    reg = _registry_two_built()
    reg.activate("v1")
    assert reg.active_version() == "v1"
    active_flags = [r.active for r in reg.records()]
    assert active_flags.count(True) == 1
    assert reg._records["v1"].active is True
    assert reg._records["v2"].active is False


def test_register_returns_build_record() -> None:
    reg = BuildRegistry()
    rec = reg.register("v1", n_communities=7, created_at="2026-01-01T00:00:00Z")
    assert isinstance(rec, BuildRecord)
    assert rec.build_version == "v1"
    assert rec.status == "built"
    assert rec.n_communities == 7
    assert rec.active is False


def test_activate_failed_build_raises() -> None:
    reg = BuildRegistry()
    reg.register("bad", n_communities=0, created_at="2026-01-01T00:00:00Z", status="failed")
    with pytest.raises(ValueError):
        reg.activate("bad")
    assert reg.active_version() is None


def test_activate_indexing_build_raises() -> None:
    reg = BuildRegistry()
    reg.register("ix", n_communities=3, created_at="2026-01-01T00:00:00Z", status="indexing")
    with pytest.raises(ValueError):
        reg.activate("ix")


def test_activate_missing_build_raises() -> None:
    reg = BuildRegistry()
    with pytest.raises(ValueError):
        reg.activate("nope")


def test_activating_v2_flips_flags() -> None:
    reg = _registry_two_built()
    reg.activate("v1")
    reg.activate("v2")
    assert reg._records["v1"].active is False
    assert reg._records["v2"].active is True
    assert reg.active_version() == "v2"


def test_rollback_returns_v1_and_reactivates() -> None:
    reg = _registry_two_built()
    reg.activate("v1")
    reg.activate("v2")
    result = reg.rollback()
    assert result == "v1"
    assert reg.active_version() == "v1"


def test_rollback_with_no_history_raises() -> None:
    reg = _registry_two_built()
    reg.activate("v1")
    with pytest.raises(ValueError):
        reg.rollback()


def test_retain_one_of_three_prunes_two_keeps_active() -> None:
    reg = BuildRegistry()
    reg.register("v1", n_communities=1, created_at="2026-01-01T00:00:00Z")
    reg.register("v2", n_communities=2, created_at="2026-02-01T00:00:00Z")
    reg.register("v3", n_communities=3, created_at="2026-03-01T00:00:00Z")
    reg.activate("v3")
    pruned = reg.retain(1)
    assert len(pruned) == 2
    # The active newest build v3 survives; the two older builds are pruned.
    assert "v3" not in pruned
    assert reg.active_version() == "v3"
    surviving = {r.build_version for r in reg.records()}
    assert surviving == {"v3"}
    assert set(pruned) == {"v1", "v2"}


def test_retain_never_prunes_active_even_if_not_newest() -> None:
    reg = BuildRegistry()
    reg.register("v1", n_communities=1, created_at="2026-01-01T00:00:00Z")
    reg.register("v2", n_communities=2, created_at="2026-02-01T00:00:00Z")
    reg.register("v3", n_communities=3, created_at="2026-03-01T00:00:00Z")
    reg.activate("v1")
    pruned = reg.retain(1)
    # Newest 1 = v3, plus the active v1 is always protected -> only v2 pruned.
    assert pruned == ["v2"]
    assert reg.active_version() == "v1"
    assert {r.build_version for r in reg.records()} == {"v1", "v3"}


def test_retain_keeps_newest_when_none_active() -> None:
    reg = BuildRegistry()
    reg.register("v1", n_communities=1, created_at="2026-01-01T00:00:00Z")
    reg.register("v2", n_communities=2, created_at="2026-02-01T00:00:00Z")
    reg.register("v3", n_communities=3, created_at="2026-03-01T00:00:00Z")
    pruned = reg.retain(2)
    assert pruned == ["v1"]
    assert {r.build_version for r in reg.records()} == {"v2", "v3"}


def test_register_duplicate_raises() -> None:
    reg = BuildRegistry()
    reg.register("v1", n_communities=1, created_at="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        reg.register("v1", n_communities=9, created_at="2026-05-01T00:00:00Z")


def test_register_invalid_status_raises() -> None:
    reg = BuildRegistry()
    with pytest.raises(ValueError):
        reg.register("v1", n_communities=1, created_at="2026-01-01T00:00:00Z", status="weird")


def test_as_dict_active_is_bool() -> None:
    reg = _registry_two_built()
    reg.activate("v1")
    d = reg._records["v1"].as_dict()
    assert isinstance(d["active"], bool)
    assert d["active"] is True
    assert d["build_version"] == "v1"
    assert d["n_communities"] == 10
    assert reg._records["v2"].as_dict()["active"] is False


def test_active_version_none_initially() -> None:
    reg = _registry_two_built()
    assert reg.active_version() is None


def test_rollback_then_forward_again() -> None:
    reg = _registry_two_built()
    reg.activate("v1")
    reg.activate("v2")
    assert reg.rollback() == "v1"
    reg.activate("v2")
    assert reg.active_version() == "v2"
    assert reg.rollback() == "v1"
