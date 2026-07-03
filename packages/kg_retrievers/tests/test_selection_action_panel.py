"""Tests for the §17.8 selection action panel view-model (hand-checkable)."""

from __future__ import annotations

from typing import Any

from kg_retrievers.selection_action_panel import SelectionPanel, build_selection_panel


def _graph() -> dict[str, Any]:
    """Three nodes (n1 Material, n2 Gap, n3 Material) with two edges."""
    return {
        "nodes": [
            {"id": "n1", "type": "Material", "confidence": 0.8},
            {"id": "n2", "type": "Gap", "confidence": 0.6},
            {"id": "n3", "type": "Material", "confidence": 0.5},
        ],
        "edges": [
            {"source": "n1", "target": "n2"},  # both selectable
            {"source": "n2", "target": "n3"},  # crosses to unselected n3
        ],
    }


def test_node_count_selecting_two_of_three() -> None:
    panel = build_selection_panel(_graph(), ["n1", "n2"])
    assert panel.node_count == 2
    assert panel.node_ids == ("n1", "n2")


def test_induced_edge_excludes_edge_to_unselected_node() -> None:
    # n1-n2 both selected -> counted; n2-n3 crosses to unselected n3 -> excluded.
    panel = build_selection_panel(_graph(), ["n1", "n2"])
    assert panel.edge_count == 1


def test_type_counts_material_and_gap() -> None:
    panel = build_selection_panel(_graph(), ["n1", "n2"])
    assert panel.type_counts == {"Material": 1, "Gap": 1}


def test_avg_confidence_is_mean() -> None:
    panel = build_selection_panel(_graph(), ["n1", "n2"])
    assert panel.avg_confidence == 0.7  # (0.8 + 0.6) / 2


def test_has_gap_appends_resolve_gaps_action() -> None:
    panel = build_selection_panel(_graph(), ["n1", "n2"])
    assert panel.has_gap is True
    assert "resolve_gaps" in panel.actions
    assert panel.actions == ("export_subgraph", "ask_agent", "resolve_gaps")


def test_no_gap_keeps_base_actions_only() -> None:
    panel = build_selection_panel(_graph(), ["n1", "n3"])
    assert panel.has_gap is False
    assert panel.actions == ("export_subgraph", "ask_agent")


def test_nonexistent_id_is_dropped() -> None:
    panel = build_selection_panel(_graph(), ["n1", "ghost"])
    assert panel.node_ids == ("n1",)
    assert panel.node_count == 1


def test_empty_selection() -> None:
    panel = build_selection_panel(_graph(), [])
    assert panel.node_ids == ()
    assert panel.node_count == 0
    assert panel.edge_count == 0
    assert panel.type_counts == {}
    assert panel.avg_confidence == 0.0
    assert panel.has_gap is False
    assert panel.actions == ("export_subgraph", "ask_agent")


def test_node_ids_are_sorted() -> None:
    panel = build_selection_panel(_graph(), ["n3", "n1"])
    assert panel.node_ids == ("n1", "n3")


def test_missing_confidence_ignored_in_mean() -> None:
    graph = {
        "nodes": [
            {"id": "a", "type": "Material", "confidence": 0.4},
            {"id": "b", "type": "Material"},  # no confidence -> ignored
        ],
        "edges": [],
    }
    panel = build_selection_panel(graph, ["a", "b"])
    assert panel.avg_confidence == 0.4


def test_as_dict_shape() -> None:
    panel = build_selection_panel(_graph(), ["n1", "n2"])
    out = panel.as_dict()
    assert out == {
        "nodeIds": ["n1", "n2"],
        "nodeCount": 2,
        "edgeCount": 1,
        "typeCounts": {"Material": 1, "Gap": 1},
        "avgConfidence": 0.7,
        "hasGap": True,
        "actions": ["export_subgraph", "ask_agent", "resolve_gaps"],
    }
    assert isinstance(panel, SelectionPanel)


def test_missing_nodes_and_edges_keys() -> None:
    panel = build_selection_panel({}, ["n1"])
    assert panel.node_ids == ()
    assert panel.edge_count == 0
    assert panel.avg_confidence == 0.0
