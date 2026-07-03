"""Tests for §17.8 path-search result highlighting (:mod:`graph_path_highlight`)."""

from __future__ import annotations

from kg_retrievers.graph_path_highlight import (
    PathHighlight,
    highlight_path,
    path_highlight_summary,
)


def _graph() -> dict[str, object]:
    """A small §5.3 GraphResponse: A-B-C chain plus an off-path node D and edge B-D.

    Path nodes: A, B, C. Off-path node: D. Edges: e_ab (A->B), e_bc (C->B, reversed
    on purpose) and e_bd (B->D, non-path).
    """
    return {
        "nodes": [
            {"id": "A", "type": "Material"},
            {"id": "B", "type": "Material"},
            {"id": "C", "type": "Material"},
            {"id": "D", "type": "Material"},
        ],
        "edges": [
            {"id": "e_ab", "source": "A", "target": "B"},
            {"id": "e_bc", "source": "C", "target": "B"},
            {"id": "e_bd", "source": "B", "target": "D"},
        ],
    }


def test_path_node_marked_onpath_with_index_order() -> None:
    out = highlight_path(_graph(), ["A", "B", "C"])
    by_id = {node["id"]: node for node in out["nodes"]}
    assert by_id["A"]["onPath"] is True and by_id["A"]["pathOrder"] == 0
    assert by_id["B"]["onPath"] is True and by_id["B"]["pathOrder"] == 1
    assert by_id["C"]["onPath"] is True and by_id["C"]["pathOrder"] == 2


def test_off_path_node_marked_false_and_no_order() -> None:
    out = highlight_path(_graph(), ["A", "B", "C"])
    by_id = {node["id"]: node for node in out["nodes"]}
    assert by_id["D"]["onPath"] is False
    assert "pathOrder" not in by_id["D"]


def test_edge_between_consecutive_nodes_onpath_regardless_of_direction() -> None:
    out = highlight_path(_graph(), ["A", "B", "C"])
    by_id = {edge["id"]: edge for edge in out["edges"]}
    # e_ab stored A->B and e_bc stored C->B (reversed) both connect a path pair.
    assert by_id["e_ab"]["onPath"] is True
    assert by_id["e_bc"]["onPath"] is True


def test_non_path_edge_marked_false() -> None:
    out = highlight_path(_graph(), ["A", "B", "C"])
    by_id = {edge["id"]: edge for edge in out["edges"]}
    assert by_id["e_bd"]["onPath"] is False


def test_input_graph_not_mutated() -> None:
    graph = _graph()
    highlight_path(graph, ["A", "B", "C"])
    assert "onPath" not in graph["nodes"][0]
    assert "onPath" not in graph["edges"][0]


def test_summary_edge_ids_in_order() -> None:
    summary = path_highlight_summary(_graph(), ["A", "B", "C"])
    assert summary.edge_ids == ("e_ab", "e_bc")
    assert summary.node_ids == ("A", "B", "C")


def test_summary_length_for_three_node_path_is_two() -> None:
    summary = path_highlight_summary(_graph(), ["A", "B", "C"])
    assert summary.length == 2


def test_summary_missing_segment_for_unconnected_pair() -> None:
    # B and D are connected (e_bd) but D and A have no edge -> pair (1,2) missing.
    summary = path_highlight_summary(_graph(), ["B", "D", "A"])
    assert summary.missing_segments == ((1, 2),)
    assert summary.edge_ids == ("e_bd",)
    assert summary.length == 2


def test_single_node_path_length_zero_no_edges() -> None:
    summary = path_highlight_summary(_graph(), ["A"])
    assert summary.length == 0
    assert summary.edge_ids == ()
    assert summary.missing_segments == ()


def test_as_dict_shape() -> None:
    summary = path_highlight_summary(_graph(), ["B", "D", "A"])
    assert summary.as_dict() == {
        "nodeIds": ["B", "D", "A"],
        "edgeIds": ["e_bd"],
        "missingSegments": [[1, 2]],
        "length": 2,
    }


def test_pathhighlight_is_frozen() -> None:
    summary = path_highlight_summary(_graph(), ["A", "B"])
    assert isinstance(summary, PathHighlight)
    try:
        summary.length = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("PathHighlight must be frozen")
