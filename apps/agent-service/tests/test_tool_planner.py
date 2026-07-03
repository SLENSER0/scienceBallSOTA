"""Tests for the §13.10 query-intent tool planner (:mod:`agent_service.tool_planner`).

Deterministic, dependency-light, hand-checkable: exercises :func:`plan_tools` over
the nine named §7.5 intents and edge inputs. Reuses the nine
:class:`~agent_service.intent_taxonomy.Intent` values (never edits that module).
"""

from __future__ import annotations

import dataclasses

import pytest
from agent_service.intent_taxonomy import ALL_INTENTS, Intent
from agent_service.tool_planner import (
    DEFAULT_STEPS,
    EVIDENCE_STEPS,
    KNOWN_TOOLS,
    ToolPlan,
    plan_tools,
)


def test_a_few_intents_yield_sensible_nonempty_step_lists() -> None:
    """Several representative intents plan a sensible, non-empty ordered step list."""
    material = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY)
    assert isinstance(material, ToolPlan)
    assert material.steps == [
        "resolve_entities",
        "hybrid_search",
        "graph_search",
        "evidence_lookup",
    ]

    gap = plan_tools(Intent.GAP_ANALYSIS)
    assert gap.steps[0] == "gap_check"  # §13.10 example: gap_analysis -> [gap_check, ...]
    assert gap.steps  # non-empty

    lit = plan_tools(Intent.LITERATURE_SUMMARY)
    assert lit.steps[0] == "global_search"  # §13.10 example: literature_summary -> [global_search,]

    method = plan_tools(Intent.METHOD_COMPARISON)
    assert "compare_practice" in method.steps
    assert len(method.steps) >= 2


def test_every_intent_plans_a_nonempty_known_step_list() -> None:
    """All nine §7.5 intents plan a non-empty list of *known* tool names, no dupes."""
    assert len(ALL_INTENTS) == 9
    for intent in ALL_INTENTS:
        plan = plan_tools(intent)
        assert plan.steps, f"{intent} planned an empty step list"
        assert all(step in KNOWN_TOOLS for step in plan.steps), f"{intent} used an unknown tool"
        assert len(plan.steps) == len(set(plan.steps)), f"{intent} has duplicate steps"


def test_steps_are_known_tool_names_and_evidence_last_for_retrieval() -> None:
    """Retrieval intents end on an evidence step (§8.3); schema_help is the exception."""
    for intent in ALL_INTENTS:
        plan = plan_tools(intent)
        if intent is Intent.SCHEMA_HELP:
            assert plan.steps == ["graph_schema"]  # no-retrieval intent
            assert plan.steps[-1] not in EVIDENCE_STEPS
        else:
            assert plan.steps[-1] in EVIDENCE_STEPS, f"{intent} must end on evidence"


def test_unknown_intent_yields_default_plan() -> None:
    """An unrecognised intent name degrades to the default plan, not a crash."""
    plan = plan_tools("totally_not_a_real_intent")
    assert plan.steps == list(DEFAULT_STEPS)
    assert plan.intent == "totally_not_a_real_intent"
    assert all(step in KNOWN_TOOLS for step in plan.steps)
    assert not plan.parallel  # single graph strategy


def test_none_intent_yields_default_plan() -> None:
    """A ``None`` intent tolerated → default plan with an empty intent label."""
    plan = plan_tools(None)
    assert plan.steps == list(DEFAULT_STEPS)
    assert plan.intent == ""


def test_parallel_flag_set_for_multi_strategy_intents() -> None:
    """Multi-strategy intents fan out (parallel True); single-strategy ones do not."""
    multi = [
        Intent.MATERIAL_REGIME_PROPERTY_QUERY,  # hybrid_search + graph_search
        Intent.GAP_ANALYSIS,  # gap_check + graph_search
        Intent.CONTRADICTION_ANALYSIS,  # detect_contradictions + graph_search
        Intent.METHOD_COMPARISON,  # graph_search + compare_practice
        Intent.LITERATURE_SUMMARY,  # global_search + hybrid_search
    ]
    single = [
        Intent.ENTITY_EXPLORATION,  # only graph_search is an independent strategy
        Intent.EXPERIMENT_LOOKUP,
        Intent.EVIDENCE_REQUEST,
        Intent.SCHEMA_HELP,  # no retrieval at all
    ]
    for intent in multi:
        assert plan_tools(intent).parallel is True, f"{intent} should be parallel"
    for intent in single:
        assert plan_tools(intent).parallel is False, f"{intent} should be sequential"


def test_deterministic_same_input_same_plan() -> None:
    """Same ``(intent, query)`` always yields an equal plan (no hidden state / RNG)."""
    q = "твёрдость сплава Al-Cu после старения при 180°C"
    first = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY, q)
    second = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY, q)
    assert first == second
    assert first.as_dict() == second.as_dict()
    # And equal across the string-vs-enum spelling of the same intent.
    via_str = plan_tools("material_regime_property_query", q)
    assert via_str.as_dict() == first.as_dict()


def test_as_dict_shape() -> None:
    """``as_dict`` exposes exactly ``{intent, steps, parallel}`` with copied steps."""
    plan = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY)
    d = plan.as_dict()
    assert set(d) == {"intent", "steps", "parallel"}
    assert d["intent"] == "material_regime_property_query"
    assert isinstance(d["steps"], list) and d["steps"] == plan.steps
    assert isinstance(d["parallel"], bool)
    # The dict must own a *copy* of the steps (mutating it must not touch the plan).
    d["steps"].append("mutated")
    assert "mutated" not in plan.steps


def test_evidence_step_present_for_evidence_request() -> None:
    """The evidence_request plan surfaces provenance (§8.3 evidence-first)."""
    plan = plan_tools(Intent.EVIDENCE_REQUEST)
    assert EVIDENCE_STEPS & set(plan.steps), "evidence_request must include an evidence step"
    assert "get_evidence_by_ids" in plan.steps
    assert plan.steps[-1] in EVIDENCE_STEPS


def test_empty_query_tolerated() -> None:
    """An empty query is fine and yields the base (no numeric_filter) plan."""
    default = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY)
    empty = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY, "")
    assert empty.steps == default.steps
    assert "numeric_filter" not in empty.steps


def test_measurement_query_adds_numeric_filter_before_evidence() -> None:
    """A number+unit query refines a measurement intent with numeric_filter (Mode A)."""
    plan = plan_tools(Intent.MATERIAL_REGIME_PROPERTY_QUERY, "предел прочности 250 МПа")
    assert "numeric_filter" in plan.steps
    assert plan.steps[-1] in EVIDENCE_STEPS  # evidence stays last (§8.3)
    assert plan.steps.index("numeric_filter") < plan.steps.index("evidence_lookup")
    # Non-measurement intents ignore the numeric hint.
    lit = plan_tools(Intent.LITERATURE_SUMMARY, "обзор при 250 МПа")
    assert "numeric_filter" not in lit.steps


def test_toolplan_is_frozen() -> None:
    """``ToolPlan`` is an immutable frozen dataclass (house style)."""
    plan = plan_tools(Intent.SCHEMA_HELP)
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.parallel = True  # type: ignore[misc]
