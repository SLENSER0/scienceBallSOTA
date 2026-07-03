"""Tests for the document outline / TOC tree (§5.7)."""

from __future__ import annotations

from kg_extractors.section_outline import OutlineNode, build_outline, total_chunks


def _chunk(*path: str) -> dict:
    """Tiny helper — a chunk that lives at ``path``."""
    return {"section_path": list(path)}


def test_results_with_mechanism_child() -> None:
    """[Results], [Results, Mech], [Results, Mech] → root + one child."""
    forest = build_outline(
        [_chunk("Results"), _chunk("Results", "Mech"), _chunk("Results", "Mech")]
    )
    assert len(forest) == 1
    root = forest[0]
    assert root.title == "Results"
    assert len(root.children) == 1
    mech = root.children[0]
    assert mech.title == "Mech"


def test_chunk_count_is_exact_node_only() -> None:
    """Counts credit the node a chunk *ends* on, not its ancestors."""
    forest = build_outline(
        [_chunk("Results"), _chunk("Results", "Mech"), _chunk("Results", "Mech")]
    )
    root = forest[0]
    mech = root.children[0]
    assert root.chunk_count == 1
    assert mech.chunk_count == 2


def test_total_chunks_rolls_up_subtree() -> None:
    """total_chunks(root) sums the node and all descendants (1 + 2 == 3)."""
    forest = build_outline(
        [_chunk("Results"), _chunk("Results", "Mech"), _chunk("Results", "Mech")]
    )
    root = forest[0]
    assert total_chunks(root) == 3
    assert total_chunks(root.children[0]) == 2


def test_child_path_is_full_chain() -> None:
    """A child's path is the full heading chain from its root."""
    forest = build_outline([_chunk("Results", "Mech")])
    mech = forest[0].children[0]
    assert mech.path == ("Results", "Mech")
    assert mech.path[-1] == mech.title
    assert forest[0].path == ("Results",)


def test_sibling_roots_form_a_forest() -> None:
    """Distinct top headings [A] and [B] give a 2-element forest."""
    forest = build_outline([_chunk("A"), _chunk("B")])
    assert len(forest) == 2
    assert [root.title for root in forest] == ["A", "B"]
    assert all(root.depth == 0 for root in forest)


def test_deep_path_builds_intermediate_chain() -> None:
    """[A, B, C] builds a depth-0/1/2 chain; only C carries the count."""
    forest = build_outline([_chunk("A", "B", "C")])
    assert len(forest) == 1
    node_a = forest[0]
    node_b = node_a.children[0]
    node_c = node_b.children[0]
    assert (node_a.depth, node_b.depth, node_c.depth) == (0, 1, 2)
    assert node_a.title == "A"
    assert node_b.title == "B"
    assert node_c.title == "C"
    assert node_c.path == ("A", "B", "C")
    # Only the leaf a chunk ends on is counted; intermediates stay 0.
    assert node_a.chunk_count == 0
    assert node_b.chunk_count == 0
    assert node_c.chunk_count == 1
    assert total_chunks(node_a) == 1


def test_as_dict_leaf_has_empty_children_list() -> None:
    """as_dict() of a leaf renders children as an empty list."""
    forest = build_outline([_chunk("Results", "Mech")])
    mech = forest[0].children[0]
    rendered = mech.as_dict()
    assert rendered == {
        "title": "Mech",
        "depth": 1,
        "path": ["Results", "Mech"],
        "chunk_count": 1,
        "children": [],
    }


def test_as_dict_recurses_into_children() -> None:
    """as_dict() nests children recursively under the root."""
    forest = build_outline([_chunk("Results"), _chunk("Results", "Mech")])
    rendered = forest[0].as_dict()
    assert rendered["title"] == "Results"
    assert rendered["chunk_count"] == 1
    assert len(rendered["children"]) == 1
    assert rendered["children"][0]["title"] == "Mech"


def test_empty_chunks_yield_empty_forest() -> None:
    """No chunks → empty tuple."""
    assert build_outline([]) == ()


def test_chunks_without_section_path_are_skipped() -> None:
    """Empty or missing section_path contributes no node."""
    assert build_outline([{"section_path": []}, {}]) == ()
    forest = build_outline([_chunk("A"), {"section_path": []}])
    assert len(forest) == 1
    assert forest[0].title == "A"


def test_outline_node_is_frozen() -> None:
    """OutlineNode is immutable — attribute writes raise."""
    node = OutlineNode(title="X", depth=0, path=("X",), chunk_count=0, children=())
    try:
        node.chunk_count = 5  # type: ignore[misc]
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("OutlineNode should be frozen")
