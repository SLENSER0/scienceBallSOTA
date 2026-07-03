"""Tests for lasso/box selection → subgraph + ask-agent context (§17.8).

Проверяем чистую функцию ``select_subgraph`` над §5.3 GraphResponse dict: отбор
узлов по явному множеству id, отбрасывание рёбер с эндпоинтом вне выделения,
формирование ``ask_context`` (sorted ids, labels, type counts) и ``as_dict()``.
"""

from __future__ import annotations

from kg_retrievers.graph_selection_action import (
    SelectionSubgraph,
    select_subgraph,
)


def _graph() -> dict:
    """3 nodes (A, B Material; C Paper) with edges A→B, A→C, B→A (§5.3)."""
    return {
        "nodes": [
            {"id": "A", "type": "Material", "label": "Al-6061"},
            {"id": "B", "type": "Material", "label": "Ti-64"},
            {"id": "C", "type": "Paper", "label": "Smith 2020"},
        ],
        "edges": [
            {"id": "e1", "source": "A", "target": "B", "type": "SIMILAR"},
            {"id": "e2", "source": "A", "target": "C", "type": "CITED_IN"},
            {"id": "e3", "source": "B", "target": "A", "type": "INFERRED"},
        ],
    }


def test_selecting_ab_keeps_exactly_a_and_b() -> None:
    result = select_subgraph(_graph(), {"A", "B"})
    assert {n["id"] for n in result.nodes} == {"A", "B"}
    assert len(result.nodes) == 2


def test_edge_to_unselected_node_is_dropped() -> None:
    # A→C: C not selected -> orphan/external edge dropped.
    result = select_subgraph(_graph(), {"A", "B"})
    assert "e2" not in {e["id"] for e in result.edges}


def test_internal_edge_between_selected_nodes_is_kept() -> None:
    # A→B (e1) and B→A (e3) are both internal to {A, B}.
    result = select_subgraph(_graph(), {"A", "B"})
    kept = {e["id"] for e in result.edges}
    assert "e1" in kept
    assert "e3" in kept


def test_ask_context_node_ids_sorted_ascending() -> None:
    # Selection order B, A, C but nodeIds must come out sorted.
    result = select_subgraph(_graph(), {"B", "A", "C"})
    assert result.ask_context["nodeIds"] == ["A", "B", "C"]
    assert result.ask_context["nodeIds"] == sorted(result.ask_context["nodeIds"])


def test_ask_context_types_count_matches_selected_nodes() -> None:
    result = select_subgraph(_graph(), {"A", "B", "C"})
    # A, B Material; C Paper.
    assert result.ask_context["types"] == {"Material": 2, "Paper": 1}
    result_ab = select_subgraph(_graph(), {"A", "B"})
    assert result_ab.ask_context["types"] == {"Material": 2}


def test_ask_context_labels_in_node_order() -> None:
    result = select_subgraph(_graph(), {"A", "B", "C"})
    # Nodes preserve §5.3 input order A, B, C.
    assert result.ask_context["labels"] == ["Al-6061", "Ti-64", "Smith 2020"]


def test_ask_context_counts() -> None:
    result = select_subgraph(_graph(), {"A", "B"})
    assert result.ask_context["nodeCount"] == 2
    # e1, e3 internal; e2 dropped.
    assert result.ask_context["edgeCount"] == 2


def test_empty_selection_yields_empty_subgraph() -> None:
    result = select_subgraph(_graph(), set())
    assert result.nodes == ()
    assert result.edges == ()
    assert result.ask_context["nodeCount"] == 0
    assert result.ask_context["edgeCount"] == 0
    assert result.ask_context["nodeIds"] == []
    assert result.ask_context["types"] == {}


def test_selecting_all_ids_keeps_all_original_edges() -> None:
    result = select_subgraph(_graph(), {"A", "B", "C"})
    assert len(result.nodes) == 3
    assert {e["id"] for e in result.edges} == {"e1", "e2", "e3"}
    assert result.ask_context["edgeCount"] == 3


def test_as_dict_shape_and_lengths() -> None:
    result = select_subgraph(_graph(), {"A", "B"})
    d = result.as_dict()
    assert set(d) == {"nodes", "edges", "askContext"}
    # nodes length equals selected (present) node count.
    assert len(d["nodes"]) == 2
    assert d["askContext"]["nodeCount"] == 2


def test_frozen_dataclass() -> None:
    result = select_subgraph(_graph(), {"A"})
    assert isinstance(result, SelectionSubgraph)
    try:
        result.nodes = ()  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("SelectionSubgraph must be frozen")


def test_selection_id_not_in_graph_is_ignored() -> None:
    # 'Z' isn't a real node; only A survives, no edges internal to {A}.
    result = select_subgraph(_graph(), {"A", "Z"})
    assert {n["id"] for n in result.nodes} == {"A"}
    assert result.edges == ()
    assert result.ask_context["nodeIds"] == ["A"]


def test_node_without_label_falls_back_to_id() -> None:
    graph = {
        "nodes": [{"id": "X", "type": "Material"}],
        "edges": [],
    }
    result = select_subgraph(graph, {"X"})
    assert result.ask_context["labels"] == ["X"]
