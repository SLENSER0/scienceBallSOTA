"""Tests for §11.6 community hierarchy roll-up aggregation."""

from __future__ import annotations

from kg_retrievers.community_hierarchy_rollup import RolledCommunity, rollup


def _fixture() -> dict[int, RolledCommunity]:
    own_members = {10: ["a", "b"], 11: ["c"], 1: []}
    parent_of = {10: 1, 11: 1}
    docs_of = {10: ["d1"], 11: ["d2"]}
    return rollup(own_members, parent_of, docs_of)


def test_parent_unions_all_descendant_members() -> None:
    assert _fixture()[1].all_members == ("a", "b", "c")


def test_parent_subtree_size() -> None:
    assert _fixture()[1].subtree_size == 3


def test_parent_unions_all_descendant_docs() -> None:
    assert _fixture()[1].all_docs == ("d1", "d2")


def test_leaf_only_its_own() -> None:
    rolled = _fixture()
    assert rolled[10].all_members == ("a", "b")
    assert rolled[10].subtree_size == 2


def test_leaf_present_even_without_parent_entry() -> None:
    # community 10 is a child in parent_of but never a key of own child-map;
    # it still appears as its own leaf node in the result.
    assert 10 in _fixture()


def test_singleton_no_parents() -> None:
    rolled = rollup({5: ["x"]}, {})
    assert rolled[5].all_members == ("x",)
    assert rolled[5].subtree_size == 1


def test_as_dict_subtree_size() -> None:
    assert _fixture()[1].as_dict()["subtree_size"] == 3


def test_as_dict_sorted_tuples() -> None:
    d = rollup({1: ["b", "a"]}, {})[1].as_dict()
    assert d["own_members"] == ["a", "b"]
    assert d["all_members"] == ["a", "b"]


def test_cycle_safe() -> None:
    # parent_of forms a 2-cycle: 1->2 and 2->1. Roll-up must terminate.
    rolled = rollup({1: ["p"], 2: ["q"]}, {1: 2, 2: 1})
    assert rolled[1].subtree_size == 2
    assert rolled[1].all_members == ("p", "q")


def test_three_level_rollup() -> None:
    # 100 -> 10 -> 1 : grandparent must see the leaf's member.
    rolled = rollup(
        {100: ["z"], 10: ["y"], 1: ["x"]},
        {100: 10, 10: 1},
    )
    assert rolled[1].all_members == ("x", "y", "z")
    assert rolled[10].all_members == ("y", "z")
    assert rolled[100].all_members == ("z",)
