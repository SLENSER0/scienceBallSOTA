"""Tests for :mod:`agent_service.plan_router` — §7.2 ROUTE branch router (§13.8).

Hand-checked against the STRATEGY_TO_BRANCH map: dedup, order preservation,
unknown-skip, empty fallback and the ``multi`` flag on :class:`RoutePlan`.
"""

from __future__ import annotations

from agent_service.plan_router import (
    DEFAULT_BRANCH,
    STRATEGY_TO_BRANCH,
    RoutePlan,
    build_route,
    route_after_plan,
)


def test_single_cypher_template_to_structured() -> None:
    # Assertion (1): один cypher_template → structured_retrieval.
    assert route_after_plan(["cypher_template"]) == ["structured_retrieval"]


def test_cypher_and_graph_algo_collapse_to_one() -> None:
    # Assertion (2): оба → structured_retrieval, дубль свёрнут в одну ветвь.
    assert route_after_plan(["cypher_template", "graph_algo"]) == ["structured_retrieval"]


def test_graphrag_community_to_graphrag_search() -> None:
    # Assertion (3).
    assert route_after_plan(["graphrag_community"]) == ["graphrag_search"]


def test_gap_scan_to_gap_analyzer() -> None:
    # Assertion (4).
    assert route_after_plan(["gap_scan"]) == ["gap_analyzer"]


def test_empty_input_falls_back_to_hybrid() -> None:
    # Assertion (5): пустой ввод → запасная ветвь hybrid_retrieval.
    assert route_after_plan([]) == ["hybrid_retrieval"]
    assert DEFAULT_BRANCH == "hybrid_retrieval"


def test_unknown_strategy_skipped() -> None:
    # Assertion (6): неизвестная 'foo' пропускается; остаётся только известная.
    assert route_after_plan(["foo", "cypher_template"]) == ["structured_retrieval"]
    # 'foo' в одиночку → пусто → запасная ветвь.
    assert route_after_plan(["foo"]) == ["hybrid_retrieval"]


def test_multi_strategy_three_branches_and_multi_flag() -> None:
    # Assertion (7): три разные стратегии → три ветви, build_route().multi True.
    strategy = ["cypher_template", "hybrid_chunks", "gap_scan"]
    branches = route_after_plan(strategy)
    assert branches == ["structured_retrieval", "hybrid_retrieval", "gap_analyzer"]
    plan = build_route(strategy)
    assert plan.branches == ("structured_retrieval", "hybrid_retrieval", "gap_analyzer")
    assert plan.multi is True


def test_order_preserved_first_seen() -> None:
    # Assertion (8): порядок первого появления сохраняется несмотря на дедуп.
    strategy = ["hybrid_chunks", "cypher_template", "evidence_lookup", "graph_algo"]
    # hybrid first, then structured; later dups of each are dropped.
    assert route_after_plan(strategy) == ["hybrid_retrieval", "structured_retrieval"]


def test_evidence_lookup_maps_to_hybrid() -> None:
    assert route_after_plan(["evidence_lookup"]) == ["hybrid_retrieval"]


def test_build_route_single_branch_not_multi() -> None:
    plan = build_route(["cypher_template"])
    assert plan.multi is False
    assert plan.branches == ("structured_retrieval",)


def test_build_route_empty_fallback_not_multi() -> None:
    plan = build_route([])
    assert plan.branches == ("hybrid_retrieval",)
    assert plan.multi is False


def test_routeplan_is_frozen_and_as_dict() -> None:
    plan = RoutePlan(branches=("structured_retrieval", "gap_analyzer"), multi=True)
    assert plan.as_dict() == {
        "branches": ["structured_retrieval", "gap_analyzer"],
        "multi": True,
    }
    # Frozen dataclass → assignment must raise.
    import dataclasses

    try:
        plan.multi = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guards the frozen contract
        raise AssertionError("RoutePlan must be frozen")


def test_strategy_map_covers_all_documented_strategies() -> None:
    # The six §7.2 strategies map onto exactly four distinct branches.
    assert set(STRATEGY_TO_BRANCH) == {
        "cypher_template",
        "graph_algo",
        "hybrid_chunks",
        "evidence_lookup",
        "graphrag_community",
        "gap_scan",
    }
    assert set(STRATEGY_TO_BRANCH.values()) == {
        "structured_retrieval",
        "hybrid_retrieval",
        "graphrag_search",
        "gap_analyzer",
    }
