"""Pure-python hierarchy navigation (§11.14 навигация по иерархии)."""

from __future__ import annotations

from kg_retrievers.hierarchy_nav import (
    HierarchyView,
    NavNode,
    children_of,
    parent_of,
    path_to_root,
)


def _hierarchy() -> dict[int, list[dict]]:
    # A hand-checkable 3-level tree:
    #   R1 -> {C1 -> {G1, G2}, C2}   (R1 spans a,b,c,d)
    #   R2 -> {C3}                   (R2 spans e,f)
    return {
        0: [
            {"id": "R1", "parent": None, "members": ["a", "b", "c", "d"]},
            {"id": "R2", "parent": None, "members": ["e", "f"]},
        ],
        1: [
            {"id": "C1", "parent": "R1", "members": ["a", "b"]},
            {"id": "C2", "parent": "R1", "members": ["c", "d"]},
            {"id": "C3", "parent": "R2", "members": ["e", "f"]},
        ],
        2: [
            {"id": "G1", "parent": "C1", "members": ["a"]},
            {"id": "G2", "parent": "C1", "members": ["b"]},
        ],
    }


def test_children_of_lists_direct_children() -> None:
    h = _hierarchy()
    assert children_of(h, "R1") == ["C1", "C2"]
    assert children_of(h, "R2") == ["C3"]
    assert children_of(h, "C1") == ["G1", "G2"]


def test_children_of_leaf_is_empty() -> None:
    h = _hierarchy()
    # G1/G2 and C2/C3 are leaves — no nested communities.
    assert children_of(h, "G1") == []
    assert children_of(h, "C2") == []
    assert children_of(h, "C3") == []


def test_parent_of_lookup() -> None:
    h = _hierarchy()
    assert parent_of(h, "C1") == "R1"
    assert parent_of(h, "C3") == "R2"
    assert parent_of(h, "G2") == "C1"


def test_root_has_no_parent() -> None:
    h = _hierarchy()
    assert parent_of(h, "R1") is None
    assert parent_of(h, "R2") is None


def test_unknown_ids_are_empty_or_none() -> None:
    h = _hierarchy()
    assert children_of(h, "nope") == []
    assert parent_of(h, "nope") is None
    assert path_to_root(h, "nope") == []


def test_path_to_root_from_root_is_singleton() -> None:
    h = _hierarchy()
    assert path_to_root(h, "R1") == ["R1"]
    assert path_to_root(h, "R2") == ["R2"]


def test_path_to_root_multi_level() -> None:
    h = _hierarchy()
    # deepest node walks up through every ancestor to the root, inclusive.
    assert path_to_root(h, "G1") == ["G1", "C1", "R1"]
    assert path_to_root(h, "C3") == ["C3", "R2"]


def test_as_dict_shape() -> None:
    view = HierarchyView.from_levels(_hierarchy())
    d = view.as_dict()
    assert d["n_nodes"] == 7
    assert d["n_levels"] == 3
    assert d["roots"] == ["R1", "R2"]
    assert len(d["nodes"]) == 7
    first = d["nodes"][0]
    assert first == {
        "node_id": "R1",
        "level": 0,
        "parent_id": None,
        "member_ids": ["a", "b", "c", "d"],
    }
    # NavNode.as_dict copies the members list (no shared mutable state).
    node = NavNode("X", 0, None, ("m",))
    nd = node.as_dict()
    nd["member_ids"].append("mut")
    assert node.member_ids == ("m",)


def test_view_is_accepted_like_a_levels_dict() -> None:
    # A pre-normalised HierarchyView drives the same navigation as the raw dict.
    view = HierarchyView.from_levels(_hierarchy())
    assert children_of(view, "R1") == ["C1", "C2"]
    assert parent_of(view, "G1") == "C1"
    assert path_to_root(view, "G1") == ["G1", "C1", "R1"]


def test_accepts_community_hierarchy_key_aliases() -> None:
    # community_hierarchy.HierarchyNode.as_dict emits community_id/parent_id/
    # member_ids — grouping those by level must navigate identically.
    aliased = {
        0: [{"community_id": "R1", "parent_id": None, "member_ids": ["a", "b"]}],
        1: [{"community_id": "C1", "parent_id": "R1", "member_ids": ["a"]}],
    }
    assert children_of(aliased, "R1") == ["C1"]
    assert parent_of(aliased, "C1") == "R1"
    assert path_to_root(aliased, "C1") == ["C1", "R1"]


def test_path_to_root_is_cycle_safe() -> None:
    # A malformed hierarchy with a parent cycle must terminate, not hang.
    cyclic = {
        0: [{"id": "A", "parent": "B", "members": []}],
        1: [{"id": "B", "parent": "A", "members": []}],
    }
    path = path_to_root(cyclic, "A")
    assert path == ["A", "B"]
    assert len(path) == len(set(path))  # each node visited at most once
