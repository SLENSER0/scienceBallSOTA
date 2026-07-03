"""Boundary/bridge detection over two triangles joined by one edge (§11.6).

Fixture — hand-checkable:

    triangle A = {1, 2, 3}   community 0
    triangle B = {4, 5, 6}   community 1
    bridge edge 3-4          crosses the community boundary

Only nodes 3 and 4 touch a foreign community, so they are the boundary entities:

    node 3: home=0, external={1}, external_degree=1, internal_degree=2 (to 1,2)
    node 4: home=1, external={0}, external_degree=1, internal_degree=2 (to 5,6)

Interior nodes 1,2,5,6 have external_degree 0 and are excluded. The two boundary
entities tie on bridge_score(1) and external_degree(1); entity_id asc breaks the
tie, so ``top_bridges(..., 1) == ['3']``.
"""

from __future__ import annotations

from kg_retrievers.community_boundary_entities import (
    BoundaryEntity,
    find_boundary_entities,
    top_bridges,
)

# Two triangles + one bridge (3-4).
_EDGES: list[tuple[str, str]] = [
    ("1", "2"),
    ("2", "3"),
    ("1", "3"),
    ("4", "5"),
    ("5", "6"),
    ("4", "6"),
    ("3", "4"),
]
_MEMBERSHIP: dict[str, int] = {
    "1": 0,
    "2": 0,
    "3": 0,
    "4": 1,
    "5": 1,
    "6": 1,
}


def test_boundary_entity_set_is_just_the_bridge_endpoints() -> None:
    found = find_boundary_entities(_EDGES, _MEMBERSHIP)
    assert {b.entity_id for b in found} == {"3", "4"}


def test_node_three_fields_are_hand_checked() -> None:
    found = find_boundary_entities(_EDGES, _MEMBERSHIP)
    node3 = next(b for b in found if b.entity_id == "3")
    assert node3.home_community == _MEMBERSHIP["3"]
    assert node3.external_communities == (_MEMBERSHIP["4"],)
    assert node3.external_degree == 1
    assert node3.internal_degree == 2
    assert node3.bridge_score == 1


def test_node_four_mirrors_node_three() -> None:
    found = find_boundary_entities(_EDGES, _MEMBERSHIP)
    node4 = next(b for b in found if b.entity_id == "4")
    assert node4.home_community == _MEMBERSHIP["4"]
    assert node4.external_communities == (_MEMBERSHIP["3"],)
    assert node4.external_degree == 1
    assert node4.internal_degree == 2
    assert node4.bridge_score == 1


def test_interior_node_one_is_absent() -> None:
    found = find_boundary_entities(_EDGES, _MEMBERSHIP)
    assert "1" not in {b.entity_id for b in found}


def test_top_bridges_tie_break_is_entity_id_ascending() -> None:
    assert top_bridges(_EDGES, _MEMBERSHIP, 1) == ["3"]


def test_top_bridges_returns_both_in_order() -> None:
    assert top_bridges(_EDGES, _MEMBERSHIP, 5) == ["3", "4"]


def test_top_bridges_non_positive_k_is_empty() -> None:
    assert top_bridges(_EDGES, _MEMBERSHIP, 0) == []


def test_empty_inputs_yield_empty_list() -> None:
    assert find_boundary_entities([], {}) == []


def test_as_dict_bridge_score() -> None:
    found = find_boundary_entities(_EDGES, _MEMBERSHIP)
    node3 = next(b for b in found if b.entity_id == "3")
    assert node3.as_dict()["bridge_score"] == 1


def test_sort_order_bridge_score_then_external_degree_then_id() -> None:
    # Node 'a' reaches two foreign communities (score 2); 'b' reaches one but with
    # higher external_degree; tie-only nodes fall back to entity_id.
    edges = [
        ("a", "x"),  # a(0) -> x(1)
        ("a", "y"),  # a(0) -> y(2)
        ("b", "p"),  # b(0) -> p(1)
        ("b", "q"),  # b(0) -> q(1)
        ("c", "r"),  # c(0) -> r(1)
    ]
    membership = {
        "a": 0,
        "b": 0,
        "c": 0,
        "x": 1,
        "y": 2,
        "p": 1,
        "q": 1,
        "r": 1,
    }
    ordered = [b.entity_id for b in find_boundary_entities(edges, membership)]
    # a: score 2; b: score 1 deg 2; c: score 1 deg 1 -> a, b, c.
    assert ordered[:3] == ["a", "b", "c"]
    assert isinstance(find_boundary_entities(edges, membership)[0], BoundaryEntity)
