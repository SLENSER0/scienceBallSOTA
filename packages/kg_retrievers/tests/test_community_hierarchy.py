"""Hierarchical community detection (§11.6 иерархия сообществ)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.community_hierarchy import (
    CommunityHierarchy,
    HierarchyNode,
    build_hierarchy,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


def _seed_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    return store


def test_hierarchy_has_at_least_one_level0_node() -> None:
    store = _seed_store()
    try:
        h = build_hierarchy(store)
        assert isinstance(h, CommunityHierarchy)
        roots = h.at_level(0)
        assert len(roots) >= 1
        # roots are true roots: no parent.
        assert all(r.parent_id is None for r in roots)
    finally:
        store.close()


def test_fine_members_are_subset_of_parent() -> None:
    store = _seed_store()
    try:
        h = build_hierarchy(store)
        fine = h.at_level(1)
        # the seed splits at least one super-community, so this is non-vacuous.
        assert fine, "expected the seed graph to produce level-1 sub-communities"
        for child in fine:
            parent = h.node(child.parent_id or "")
            assert parent is not None
            assert set(child.member_ids) <= set(parent.member_ids)
    finally:
        store.close()


def test_parent_of_and_children_of_are_consistent() -> None:
    store = _seed_store()
    try:
        h = build_hierarchy(store)
        for parent in h.at_level(0):
            kids = h.children_of(parent.community_id)
            for kid_id in kids:
                # round-trip: a listed child names this parent back.
                assert h.parent_of(kid_id) == parent.community_id
        # every level-1 node appears in exactly one parent's child list.
        for child in h.at_level(1):
            assert child.community_id in h.children_of(child.parent_id or "")
        # a leaf level-0 community with no split has no children.
        assert h.children_of("does-not-exist") == []
    finally:
        store.close()


def test_sizes_are_positive_and_match_members() -> None:
    store = _seed_store()
    try:
        h = build_hierarchy(store)
        assert h.nodes  # non-empty on the seed
        for hn in h.nodes:
            assert hn.size > 0
            assert hn.size == len(hn.member_ids)
            assert len(set(hn.member_ids)) == hn.size  # no duplicate members
    finally:
        store.close()


def test_as_dict_serialises_the_tree() -> None:
    store = _seed_store()
    try:
        h = build_hierarchy(store)
        d = h.as_dict()
        assert d["levels"] == 2
        assert d["n_nodes"] == len(h.nodes)
        assert d["n_roots"] == len(h.at_level(0))
        assert isinstance(d["tree"], list) and d["tree"]
        # each serialised root exposes its children; the count matches children_of.
        for root_dict in d["tree"]:
            assert root_dict["parent_id"] is None
            assert root_dict["level"] == 0
            expected_children = h.children_of(root_dict["community_id"])
            got_children = [c["community_id"] for c in root_dict["children"]]
            assert sorted(got_children) == sorted(expected_children)
            for child_dict in root_dict["children"]:
                assert child_dict["level"] == 1
                assert child_dict["parent_id"] == root_dict["community_id"]
    finally:
        store.close()


def test_graceful_on_tiny_graph() -> None:
    # A two-node entity graph cannot be split into sub-communities: the
    # hierarchy must degrade to a single level-0 node with no level-1 nodes.
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        store.upsert_node("m:a", "Material", name="A")
        store.upsert_node("m:b", "Material", name="B")
        store.upsert_edge("m:a", "m:b", "APPLIES_TO", confidence=0.9)
        h = build_hierarchy(store)
        assert len(h.at_level(0)) == 1
        assert h.at_level(1) == []
        (root,) = h.at_level(0)
        assert root.size == 2
        assert set(root.member_ids) == {"m:a", "m:b"}
        assert h.children_of(root.community_id) == []
        # a completely empty graph yields an empty hierarchy, not an error.
        d2 = tempfile.mkdtemp()
        empty = KuzuGraphStore(str(Path(d2) / "g"))
        try:
            he = build_hierarchy(empty)
            assert he.nodes == ()
            assert he.as_dict()["n_nodes"] == 0
        finally:
            empty.close()
    finally:
        store.close()


def test_levels_one_returns_coarse_only() -> None:
    # Requesting a single level must never emit level-1 nodes (§11.6).
    store = _seed_store()
    try:
        h = build_hierarchy(store, levels=1)
        assert h.levels == 1
        assert h.at_level(1) == []
        assert len(h.at_level(0)) >= 1
        assert all(isinstance(n, HierarchyNode) for n in h.nodes)
    finally:
        store.close()
