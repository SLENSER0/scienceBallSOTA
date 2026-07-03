"""§13.10 тесты априорной оценки стоимости плана / plan cost-estimate tests."""

from __future__ import annotations

from agent_service.plan_cost_estimate import STRATEGY_COST, PlanCost, estimate_cost


def test_cypher_template_only_is_cheap() -> None:
    """(1) Один cypher_template → base_cost 1, tier 'cheap'."""
    cost = estimate_cost({"retrieval_strategy": ["cypher_template"]})
    assert cost.base_cost == 1
    assert cost.tier == "cheap"


def test_community_plus_algo_is_expensive() -> None:
    """(2) graphrag_community + graph_algo → base_cost 9, tier 'expensive'."""
    cost = estimate_cost({"retrieval_strategy": ["graphrag_community", "graph_algo"]})
    assert cost.base_cost == 4 + 5 == 9
    assert cost.tier == "expensive"


def test_enable_rerank_adds_two_to_total() -> None:
    """(3) enable_rerank добавляет 2 к total / rerank penalty is 2."""
    plan = {"retrieval_strategy": ["cypher_template"]}
    without = estimate_cost(plan, enable_rerank=False)
    with_rerank = estimate_cost(plan, enable_rerank=True)
    assert without.rerank_penalty == 0
    assert with_rerank.rerank_penalty == 2
    assert with_rerank.total == without.total + 2


def test_unknown_strategy_contributes_zero() -> None:
    """(4) Неизвестная стратегия даёт 0 к base_cost / unknown → 0."""
    cost = estimate_cost({"retrieval_strategy": ["cypher_template", "no_such_strategy"]})
    # только cypher_template = 1; неизвестная = 0
    assert cost.base_cost == 1
    assert cost.strategy_count == 2


def test_strategy_count_matches_listed() -> None:
    """(5) strategy_count равен числу перечисленных стратегий."""
    strategies = ["cypher_template", "gap_scan", "hybrid_chunks"]
    cost = estimate_cost({"retrieval_strategy": strategies})
    assert cost.strategy_count == len(strategies) == 3
    assert cost.base_cost == 1 + 2 + 3 == 6


def test_empty_plan_is_zero_and_cheap() -> None:
    """(6) Пустой план → total 0, tier 'cheap'."""
    cost = estimate_cost({})
    assert cost.strategy_count == 0
    assert cost.base_cost == 0
    assert cost.total == 0
    assert cost.tier == "cheap"


def test_total_exactly_six_is_moderate() -> None:
    """(7) total ровно 6 → tier 'moderate' (граница включительно)."""
    # gap_scan(2) + hybrid_chunks(3) = 5, +rerank(2) would exceed; use 4+2 rerank=6
    cost = estimate_cost({"retrieval_strategy": ["graphrag_community"]}, enable_rerank=True)
    assert cost.total == 4 + 2 == 6
    assert cost.tier == "moderate"


def test_strategy_cost_mapping_values() -> None:
    """Проверка самой таблицы весов / the STRATEGY_COST table is as specified."""
    assert STRATEGY_COST == {
        "cypher_template": 1,
        "evidence_lookup": 1,
        "gap_scan": 2,
        "hybrid_chunks": 3,
        "graphrag_community": 4,
        "graph_algo": 5,
    }


def test_as_dict_round_trips_all_fields() -> None:
    """as_dict возвращает все пять полей / all five fields serialised."""
    cost = estimate_cost({"retrieval_strategy": ["gap_scan"]}, enable_rerank=True)
    assert cost.as_dict() == {
        "strategy_count": 1,
        "base_cost": 2,
        "rerank_penalty": 2,
        "total": 4,
        "tier": "moderate",
    }
    assert isinstance(cost, PlanCost)
