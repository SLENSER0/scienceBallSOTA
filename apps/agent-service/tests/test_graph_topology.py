"""Tests for §13.19 graph_topology — canonical §7.2 agent graph wiring."""

from __future__ import annotations

from agent_service.graph_topology import (
    END,
    NODE_NAMES,
    RETRIEVAL_BRANCHES,
    START,
    AgentGraph,
    build_agent_graph,
    draw_mermaid,
    reachable_from,
    successors,
    validate_topology,
)


def test_nodes_contain_all_twelve_plus_start_end() -> None:
    g = build_agent_graph()
    assert len(NODE_NAMES) == 12
    for name in NODE_NAMES:
        assert name in g.nodes
    assert START in g.nodes
    assert END in g.nodes
    # START + 12 nodes + END, all distinct.
    assert len(g.nodes) == 14
    assert len(set(g.nodes)) == 14


def test_linear_prefix_edges() -> None:
    g = build_agent_graph()
    assert ("START", "preprocess_question") in g.edges
    assert ("preprocess_question", "intent_classifier") in g.edges
    assert ("intent_classifier", "entity_resolver") in g.edges
    assert ("entity_resolver", "query_planner") in g.edges


def test_route_fan_out_from_query_planner() -> None:
    g = build_agent_graph()
    succ = successors(g, "query_planner")
    for branch in RETRIEVAL_BRANCHES:
        assert branch in succ
    assert set(succ) == set(RETRIEVAL_BRANCHES)


def test_every_retrieval_branch_reaches_evidence_assembler() -> None:
    g = build_agent_graph()
    for branch in RETRIEVAL_BRANCHES:
        assert (branch, "evidence_assembler") in g.edges
        assert successors(g, branch) == ("evidence_assembler",)


def test_verifier_retry_and_forward_edges() -> None:
    g = build_agent_graph()
    assert ("evidence_assembler", "verifier") in g.edges
    assert ("verifier", "query_planner") in g.edges
    assert ("verifier", "answer_synthesizer") in g.edges
    assert set(successors(g, "verifier")) == {"query_planner", "answer_synthesizer"}


def test_tail_edges_to_end() -> None:
    g = build_agent_graph()
    assert ("answer_synthesizer", "visualization_payload") in g.edges
    assert ("visualization_payload", "END") in g.edges
    assert successors(g, "visualization_payload") == ("END",)
    # END is a sink.
    assert successors(g, "END") == ()


def test_reachable_from_start_is_full_node_set() -> None:
    g = build_agent_graph()
    assert reachable_from(g, "START") == frozenset(g.nodes)


def test_validate_topology_clean() -> None:
    assert validate_topology(build_agent_graph()) == []


def test_validate_topology_flags_unreachable_node() -> None:
    g = build_agent_graph()
    broken = AgentGraph(nodes=(*g.nodes, "orphan"), edges=g.edges)
    problems = validate_topology(broken)
    assert any("orphan" in p and "unreachable" in p for p in problems)


def test_validate_topology_flags_dangling_edge() -> None:
    g = build_agent_graph()
    broken = AgentGraph(nodes=g.nodes, edges=(*g.edges, ("verifier", "ghost")))
    problems = validate_topology(broken)
    assert any("ghost" in p and "dangling" in p for p in problems)


def test_draw_mermaid_header_and_edge_line() -> None:
    g = build_agent_graph()
    mermaid = draw_mermaid(g)
    assert mermaid.startswith("flowchart TD")
    assert "preprocess_question --> intent_classifier" in mermaid
    # One header line + one line per edge.
    assert len(mermaid.splitlines()) == 1 + len(g.edges)


def test_mermaid_has_a_line_per_edge() -> None:
    g = build_agent_graph()
    mermaid = draw_mermaid(g)
    for a, b in g.edges:
        assert f"{a} --> {b}" in mermaid


def test_as_dict_round_trips_to_same_edges() -> None:
    g = build_agent_graph()
    d = g.as_dict()
    assert d["nodes"] == list(g.nodes)
    round_tripped = tuple(tuple(pair) for pair in d["edges"])
    assert round_tripped == g.edges
    # Nodes rebuild identically too.
    rebuilt = AgentGraph(nodes=tuple(d["nodes"]), edges=round_tripped)
    assert rebuilt == g


def test_frozen_dataclass_is_immutable() -> None:
    g = build_agent_graph()
    import dataclasses

    try:
        g.nodes = ()  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("AgentGraph must be frozen")
