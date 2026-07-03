"""Tests for §11.13 community metrics over a KuzuGraphStore.

Each test builds a fresh temp store, writes ``community_id`` directly onto entity
nodes, and asserts concrete, hand-checked metric values.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kg_retrievers.community_metrics import CommunityMetrics, community_metrics
from kg_retrievers.graph_store import KuzuGraphStore


def _make_store(tmp_path: Path) -> KuzuGraphStore:
    """Fresh embedded store (schema created, no nodes yet)."""
    return KuzuGraphStore(str(tmp_path / "g"))


def _assign(store: KuzuGraphStore, plan: dict[int, int]) -> None:
    """Create ``count`` Material nodes per ``community_id`` from ``plan``."""
    n = 0
    for cid, count in plan.items():
        for _ in range(count):
            n += 1
            store.upsert_node(f"e{n}", "Material", name=f"e{n}", community_id=cid)


def test_n_communities_counts_distinct_ids(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {0: 2, 1: 2, 2: 2})  # 6 nodes across 3 distinct ids
    m = community_metrics(store)
    store.close()
    assert m.n_communities == 3


def test_sizes_per_community(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {0: 3, 1: 2, 2: 1})
    m = community_metrics(store)
    store.close()
    assert m.sizes == {0: 3, 1: 2, 2: 1}


def test_largest_is_biggest_member_count(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {5: 4, 6: 1, 7: 2})  # community 5 is the biggest
    m = community_metrics(store)
    store.close()
    assert m.largest == 4


def test_singletons_count_size_one_communities(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {0: 3, 1: 1, 2: 1, 3: 5})  # two communities of size 1
    m = community_metrics(store)
    store.close()
    assert m.singletons == 2


def test_empty_store_returns_zeros(tmp_path: Path) -> None:
    store = _make_store(tmp_path)  # schema only, no nodes
    m = community_metrics(store)
    store.close()
    assert m.n_communities == 0
    assert m.sizes == {}
    assert m.modularity_proxy == 0.0
    assert m.largest == 0
    assert m.singletons == 0
    assert m.as_dict() == {
        "n_communities": 0,
        "sizes": {},
        "modularity_proxy": 0.0,
        "largest": 0,
        "singletons": 0,
    }


def test_as_dict_reports_all_fields(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {0: 3, 1: 1})  # N = 4
    m = community_metrics(store)
    store.close()
    d = m.as_dict()
    assert d["n_communities"] == 2
    assert d["sizes"] == {0: 3, 1: 1}
    assert d["largest"] == 3
    assert d["singletons"] == 1
    assert d["modularity_proxy"] == pytest.approx((3 / 4) ** 2 + (1 / 4) ** 2)  # 0.625


def test_modularity_proxy_is_size_herfindahl(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {0: 3, 1: 2, 2: 1})  # N = 6
    m = community_metrics(store)
    store.close()
    # (3/6)^2 + (2/6)^2 + (1/6)^2 = 1/4 + 1/9 + 1/36 = 7/18
    assert m.modularity_proxy == pytest.approx(7 / 18)


def test_single_community_proxy_is_one(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {9: 5})  # one community holding every node
    m = community_metrics(store)
    store.close()
    assert m.n_communities == 1
    assert m.modularity_proxy == pytest.approx(1.0)
    assert m.largest == 5
    assert m.singletons == 0


def test_finding_summary_nodes_are_excluded(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _assign(store, {0: 2})
    # a Finding community-summary carries community_id but is not a member
    store.upsert_node("sum-0", "Finding", name="Community summary #0", community_id=0)
    m = community_metrics(store)
    store.close()
    assert m.sizes == {0: 2}  # the Finding node is not counted
    assert m.n_communities == 1
    assert m.singletons == 0


def test_from_counts_matches_direct_construction() -> None:
    m = CommunityMetrics.from_counts({2: 4, 0: 2, 1: 2})  # N = 8
    assert m.n_communities == 3
    assert m.sizes == {0: 2, 1: 2, 2: 4}  # ordered by community id
    assert m.largest == 4
    assert m.singletons == 0
    assert m.modularity_proxy == pytest.approx((2 / 8) ** 2 * 2 + (4 / 8) ** 2)
