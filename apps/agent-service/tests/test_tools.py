"""Explicit agent tools + query planner over the seed (§13.6-§13.10).

Deterministic, no LLM: build a temp Kuzu store, seed it, then assert that
``plan_query`` picks sensible tools for the four acceptance-style intents and that
each tool returns real, evidence-first results when run on the seed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_service.tools import (
    COMPARE_PRACTICE,
    EVIDENCE_LOOKUP,
    GAP_CHECK,
    GRAPH_SEARCH,
    NUMERIC_FILTER,
    TOOLS,
    args_from_intent,
    plan_query,
    run_plan,
    tool_compare_practice,
    tool_evidence_lookup,
    tool_gap_check,
    tool_graph_search,
    tool_numeric_filter,
)

from kg_common import make_id
from kg_extractors.query_parser import parse_query
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

WATER_Q = "Какие методы обессоливания воды при сульфатах 200–300 мг/л и TDS ≤1000 мг/дм³?"
COMPARE_Q = "Сравните практику закачки шахтных вод в России и за рубежом"
GAP_Q = "нет экспериментов холодный климат кучное выщелачивание никель"
NICKEL_Q = "циркуляция католита при электроэкстракции никеля, оптимальная скорость потока"


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# plan_query (§13.10): the four acceptance-style intents pick sensible tools
# ---------------------------------------------------------------------------
def test_plan_numeric_query() -> None:
    plan = plan_query(parse_query(WATER_Q))
    assert plan[0] == GRAPH_SEARCH and plan[-1] == EVIDENCE_LOOKUP
    assert NUMERIC_FILTER in plan
    assert GAP_CHECK not in plan and COMPARE_PRACTICE not in plan


def test_plan_comparison_query() -> None:
    plan = plan_query(parse_query(COMPARE_Q))
    assert COMPARE_PRACTICE in plan
    assert NUMERIC_FILTER not in plan and GAP_CHECK not in plan


def test_plan_gap_query() -> None:
    plan = plan_query(parse_query(GAP_Q))
    assert GAP_CHECK in plan
    assert NUMERIC_FILTER not in plan and COMPARE_PRACTICE not in plan


def test_plan_structured_query_is_minimal() -> None:
    # A plain structured question needs only base retrieval + evidence assembly.
    assert plan_query(parse_query(NICKEL_Q)) == [GRAPH_SEARCH, EVIDENCE_LOOKUP]


def test_plan_is_deterministic_and_ordered() -> None:
    intent = parse_query(WATER_Q)
    assert plan_query(intent) == plan_query(intent)  # pure
    plan = plan_query(intent)
    assert len(plan) == len(set(plan))  # no dupes
    # graph_search always first, evidence_lookup always last
    assert plan.index(GRAPH_SEARCH) == 0
    assert plan.index(EVIDENCE_LOOKUP) == len(plan) - 1
    # every planned name is a registered tool
    assert set(plan) <= set(TOOLS)


# ---------------------------------------------------------------------------
# Tools run on the seed (§13.6)
# ---------------------------------------------------------------------------
def test_graph_search_finds_water_solutions(store: KuzuGraphStore) -> None:
    out = tool_graph_search.run(store, {"domains": ["water_treatment"]})
    ro = make_id("TechnologySolution", "reverse osmosis desalination")
    ie = make_id("TechnologySolution", "ion exchange desalination")
    assert out["count"] >= 3
    assert ro in out["matched_ids"] and ie in out["matched_ids"]


def test_numeric_filter_applies_constraints(store: KuzuGraphStore) -> None:
    constraints = parse_query(WATER_Q).numeric_constraints
    assert constraints  # sanity: the query really carries numeric conditions
    out = tool_numeric_filter.run(store, {"constraints": constraints})
    vals = [m["value_normalized"] for m in out["measurements"]]
    assert out["count"] >= 1
    # constraints are mg/L → only mg/L measurements are targeted...
    assert all(m["normalized_unit"] == "mg/L" for m in out["measurements"])
    # ...and every survivor sits inside the 200–300 mg/L range (both bounds apply).
    assert all(200.0 <= v <= 300.0 for v in vals)
    # the TDS target of 1000 mg/L is excluded by the range constraint.
    assert 1000.0 not in vals


def test_evidence_lookup_returns_refs(store: KuzuGraphStore) -> None:
    ro = make_id("TechnologySolution", "reverse osmosis desalination")
    out = tool_evidence_lookup.run(store, {"ids": [ro]})
    assert out["count"] >= 1
    ev = out["evidence"]
    assert all(e["evidence_id"] for e in ev)
    # at least one ref carries a real document pointer (evidence-first, §8.3).
    assert any(e.get("doc_id") for e in ev)


def test_gap_check_finds_cold_heap_gap(store: KuzuGraphStore) -> None:
    out = tool_gap_check.run(store, {"domains": ["hydrometallurgy"]})
    gap = make_id("Gap", "cold heap leaching nickel gap")
    assert gap in {g["id"] for g in out["gaps"]}


def test_gap_check_reports_contradictions(store: KuzuGraphStore) -> None:
    # Unscoped gap check reports every known contradiction, incl. the Ni flow one.
    out = tool_gap_check.run(store, {})
    contra = make_id("Contradiction", "catholyte velocity conflict")
    assert contra in {c["id"] for c in out["contradictions"]}


def test_compare_practice_groups_domestic_and_foreign(store: KuzuGraphStore) -> None:
    out = tool_compare_practice.run(store, {"domains": ["environment"]})
    inj_ru = make_id("TechnologySolution", "deep well injection russia")
    inj_ca = make_id("TechnologySolution", "deep well injection canada")
    assert "russia" in out["groups"] and "foreign" in out["groups"]
    assert inj_ru in {s["id"] for s in out["groups"]["russia"]}
    assert inj_ca in {s["id"] for s in out["groups"]["foreign"]}


# ---------------------------------------------------------------------------
# End-to-end: plan → run over an intent (§13.10 wiring)
# ---------------------------------------------------------------------------
def test_run_plan_executes_gap_intent(store: KuzuGraphStore) -> None:
    intent = parse_query(GAP_Q)
    results = run_plan(store, intent)
    assert set(results) == set(plan_query(intent))
    # gap_check ran and found the seeded cold-climate heap-leaching gap.
    gap = make_id("Gap", "cold heap leaching nickel gap")
    assert gap in {g["id"] for g in results[GAP_CHECK]["gaps"]}


def test_args_from_intent_shape() -> None:
    args = args_from_intent(parse_query(COMPARE_Q))
    assert "environment" in args["domains"]
    assert args["countries"] == ["russia"]
    assert isinstance(args["terms"], list)


def test_global_search_tool(store: KuzuGraphStore) -> None:
    from agent_service.tools import GLOBAL_SEARCH, TOOLS, tool_global_search

    from kg_retrievers.community import detect_communities

    detect_communities(store)  # build community summaries
    assert GLOBAL_SEARCH in TOOLS
    out = tool_global_search.run(store, {"query": "осмос ионный обмен вода", "limit": 3})
    assert "answer" in out and "community_ids" in out
    assert out["count"] >= 1
