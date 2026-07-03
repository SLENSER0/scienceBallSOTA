"""Ordered processing-step graph shape (§3.5, §6.5)."""

from __future__ import annotations

import pytest

from kg_extractors.processing_graph import (
    GraphEdge,
    GraphNode,
    ProcessingGraph,
    steps_to_graph,
)
from kg_extractors.processing_steps import ProcessingStep, decompose_processing


def _step(index: int, operation: str | None = None) -> ProcessingStep:
    return ProcessingStep(
        step_index=index,
        operation=operation,
        temperature_c=None,
        time_h=None,
        atmosphere=None,
        cooling_rate=None,
        source_span=f"span {index}",
    )


def test_n_steps_yield_n_plus_one_nodes() -> None:
    steps = [_step(0, "smelting"), _step(1, "aging"), _step(2, "annealing")]
    graph = steps_to_graph(steps)
    # 3 step nodes + 1 regime root.
    assert len(graph.nodes) == 4
    step_nodes = [n for n in graph.nodes if n.label == "ProcessingStep"]
    assert len(step_nodes) == 3
    assert graph.nodes[0].label == "ProcessingRegime"
    assert graph.nodes[0].node_id == "regime"
    assert [n.node_id for n in step_nodes] == ["step_0", "step_1", "step_2"]


def test_has_step_and_next_step_edges() -> None:
    steps = [_step(0, "smelting"), _step(1, "aging"), _step(2, "annealing")]
    graph = steps_to_graph(steps)
    has_step = [e for e in graph.edges if e.rel == "HAS_STEP"]
    next_step = [e for e in graph.edges if e.rel == "NEXT_STEP"]
    # One HAS_STEP per step from the regime root.
    assert [(e.source, e.target) for e in has_step] == [
        ("regime", "step_0"),
        ("regime", "step_1"),
        ("regime", "step_2"),
    ]
    # NEXT_STEP chains consecutive steps only (n-1 edges).
    assert [(e.source, e.target) for e in next_step] == [
        ("step_0", "step_1"),
        ("step_1", "step_2"),
    ]


def test_single_step_no_next_edge() -> None:
    graph = steps_to_graph([_step(0, "quenching")])
    assert len(graph.nodes) == 2
    assert [e.rel for e in graph.edges] == ["HAS_STEP"]
    assert graph.edges[0].source == "regime"
    assert graph.edges[0].target == "step_0"


def test_empty_steps_only_regime_root() -> None:
    graph = steps_to_graph([])
    assert len(graph.nodes) == 1
    assert graph.nodes[0].label == "ProcessingRegime"
    assert graph.nodes[0].step_index == -1
    assert graph.edges == ()


def test_unordered_input_sorted_by_step_index() -> None:
    steps = [_step(2, "annealing"), _step(0, "smelting"), _step(1, "aging")]
    graph = steps_to_graph(steps)
    step_nodes = [n for n in graph.nodes if n.label == "ProcessingStep"]
    assert [n.step_index for n in step_nodes] == [0, 1, 2]
    assert [n.props["operation"] for n in step_nodes] == [
        "smelting",
        "aging",
        "annealing",
    ]
    next_step = [e for e in graph.edges if e.rel == "NEXT_STEP"]
    assert [(e.source, e.target) for e in next_step] == [
        ("step_0", "step_1"),
        ("step_1", "step_2"),
    ]


def test_step_props_carry_full_payload() -> None:
    step = ProcessingStep(
        step_index=0,
        operation="aging",
        temperature_c=180.0,
        time_h=2.0,
        atmosphere="argon",
        cooling_rate=None,
        source_span="aged at 180 C for 2 h in argon",
    )
    graph = steps_to_graph([step])
    node = graph.nodes[1]
    assert node.node_id == "step_0"
    assert node.props["temperature_c"] == 180.0
    assert node.props["time_h"] == 2.0
    assert node.props["atmosphere"] == "argon"
    assert node.props["operation"] == "aging"


def test_as_dict_round_trip_structure() -> None:
    graph = steps_to_graph([_step(0, "smelting"), _step(1, "aging")])
    d = graph.as_dict()
    assert set(d) == {"nodes", "edges"}
    assert len(d["nodes"]) == 3
    assert d["nodes"][0] == {
        "node_id": "regime",
        "label": "ProcessingRegime",
        "step_index": -1,
        "props": {},
    }
    assert d["edges"][0] == {"source": "regime", "target": "step_0", "rel": "HAS_STEP"}
    assert {"source": "step_0", "target": "step_1", "rel": "NEXT_STEP"} in d["edges"]


def test_graph_dataclasses_are_frozen() -> None:
    import dataclasses

    node = GraphNode(node_id="regime", label="ProcessingRegime", step_index=-1)
    edge = GraphEdge(source="regime", target="step_0", rel="HAS_STEP")
    graph = ProcessingGraph(nodes=(node,), edges=(edge,))
    # Frozen dataclasses reject attribute assignment.
    for obj in (node, edge, graph):
        with pytest.raises(dataclasses.FrozenInstanceError):
            obj.node_id = "x"  # type: ignore[misc]
    assert node.as_dict()["node_id"] == "regime"
    assert graph.as_dict()["edges"][0]["rel"] == "HAS_STEP"


def test_end_to_end_from_decompose() -> None:
    steps = decompose_processing("solution treated at 500 C then aged at 180 C for 2 h")
    graph = steps_to_graph(steps)
    step_nodes = [n for n in graph.nodes if n.label == "ProcessingStep"]
    assert len(step_nodes) == 2
    assert [n.props["operation"] for n in step_nodes] == [
        "solution_treatment",
        "aging",
    ]
    next_step = [e for e in graph.edges if e.rel == "NEXT_STEP"]
    assert [(e.source, e.target) for e in next_step] == [("step_0", "step_1")]
