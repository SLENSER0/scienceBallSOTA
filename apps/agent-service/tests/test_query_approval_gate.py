"""Tests for §13.21 approve_query HITL gate — hand-checked decisions."""

from __future__ import annotations

from agent_service.query_approval_gate import ApprovalDecision, decide_approval


def _narrow_plan() -> dict:
    """A bounded, non-broad plan that should never trip a trigger."""
    return {
        "intent": "experiment_lookup",
        "retrieval_strategy": ["vector", "graph"],
        "numeric_constraints": [{"field": "temp", "op": ">", "value": 300}],
        "entities": ["Catalyst-A"],
        "max_hops": 2,
    }


def test_hitl_off_never_needs_approval() -> None:
    # (1) enable_hitl False -> no approval even for a broad literature_summary plan.
    d = decide_approval({"intent": "literature_summary"}, enable_hitl=False)
    assert d.needs_approval is False
    assert d.reasons == ()


def test_broad_intent_flags_and_needs_approval() -> None:
    # (2) broad intent with hitl on -> 'broad_intent' and needs_approval True.
    d = decide_approval(
        {
            "intent": "literature_summary",
            "numeric_constraints": [1],
            "entities": ["X"],
            "max_hops": 1,
        },
        enable_hitl=True,
    )
    assert "broad_intent" in d.reasons
    assert d.needs_approval is True


def test_graph_algo_strategy_adds_reason() -> None:
    # (3) graph_algo strategy adds reason 'graph_algo'.
    d = decide_approval(
        {
            "intent": "experiment_lookup",
            "retrieval_strategy": ["graph_algo"],
            "numeric_constraints": [1],
            "entities": ["X"],
            "max_hops": 1,
        },
        enable_hitl=True,
    )
    assert "graph_algo" in d.reasons


def test_narrow_plan_no_approval() -> None:
    # (4) narrow plan with entities+numeric_constraints, experiment_lookup -> no approval.
    d = decide_approval(_narrow_plan(), enable_hitl=True)
    assert d.needs_approval is False
    assert d.reasons == ()


def test_deep_traversal_over_default_limit() -> None:
    # (5) max_hops 5 with default limit 3 -> 'deep_traversal'.
    d = decide_approval(
        {
            "intent": "experiment_lookup",
            "numeric_constraints": [1],
            "entities": ["X"],
            "max_hops": 5,
        },
        enable_hitl=True,
    )
    assert "deep_traversal" in d.reasons
    assert d.needs_approval is True


def test_reasons_sorted_and_deduped() -> None:
    # (6) an unbounded, broad, graph_algo, deep plan -> all four reasons, sorted, unique.
    d = decide_approval(
        {
            "intent": "broad_overview",
            "retrieval_strategy": ["graph_algo", "graph_algo"],
            "numeric_constraints": [],
            "entities": [],
            "max_hops": 9,
        },
        enable_hitl=True,
    )
    assert d.reasons == ("broad_intent", "deep_traversal", "graph_algo", "unbounded")
    assert list(d.reasons) == sorted(d.reasons)
    assert len(d.reasons) == len(set(d.reasons))


def test_interrupt_type_and_as_dict_shape() -> None:
    # (7) interrupt_type == 'approve_query' and as_dict carries the three keys.
    d = decide_approval({"intent": "experiment_lookup"}, enable_hitl=True)
    assert isinstance(d, ApprovalDecision)
    assert d.interrupt_type == "approve_query"
    assert set(d.as_dict()) == {"needs_approval", "reasons", "interrupt_type"}
    assert d.as_dict()["interrupt_type"] == "approve_query"


def test_unbounded_when_both_empty() -> None:
    # Extra: empty numeric_constraints and entities -> 'unbounded'.
    d = decide_approval(
        {"intent": "experiment_lookup", "numeric_constraints": [], "entities": []},
        enable_hitl=True,
    )
    assert "unbounded" in d.reasons
