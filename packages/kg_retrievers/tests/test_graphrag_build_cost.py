"""Tests for GraphRAG build cost accounting (§11.4/§11.13)."""

from __future__ import annotations

from kg_retrievers.graphrag_build_cost import BuildCost, accumulate_cost


def test_single_event_total_tokens() -> None:
    cost = accumulate_cost(
        [{"stage": "entities", "calls": 2, "prompt_tokens": 100, "completion_tokens": 40}]
    )
    assert cost.total_tokens == 140
    assert cost.per_stage["entities"] == 140
    assert cost.total_calls == 2


def test_two_events_same_stage_sum_into_one_entry() -> None:
    cost = accumulate_cost(
        [
            {"stage": "entities", "calls": 2, "prompt_tokens": 100, "completion_tokens": 40},
            {"stage": "entities", "calls": 3, "prompt_tokens": 50, "completion_tokens": 10},
        ]
    )
    assert list(cost.per_stage) == ["entities"]
    # 100+40 + 50+10 = 200 tokens for the single stage.
    assert cost.per_stage["entities"] == 200
    assert cost.total_calls == 5
    assert cost.total_tokens == 200


def test_total_calls_sums_across_stages() -> None:
    cost = accumulate_cost(
        [
            {"stage": "entities", "calls": 2, "prompt_tokens": 10, "completion_tokens": 5},
            {"stage": "relationships", "calls": 4, "prompt_tokens": 20, "completion_tokens": 8},
        ]
    )
    assert cost.total_calls == 6
    assert cost.prompt_tokens == 30
    assert cost.completion_tokens == 13
    assert cost.total_tokens == 43


def test_empty_events_all_zeros() -> None:
    cost = accumulate_cost([])
    assert cost.total_calls == 0
    assert cost.prompt_tokens == 0
    assert cost.completion_tokens == 0
    assert cost.total_tokens == 0
    assert cost.per_stage == {}


def test_two_different_stages_produce_two_keys() -> None:
    cost = accumulate_cost(
        [
            {"stage": "entities", "calls": 1, "prompt_tokens": 10, "completion_tokens": 2},
            {"stage": "community_reports", "calls": 1, "prompt_tokens": 30, "completion_tokens": 6},
        ]
    )
    assert set(cost.per_stage) == {"entities", "community_reports"}
    assert cost.per_stage["entities"] == 12
    assert cost.per_stage["community_reports"] == 36


def test_as_dict_total_tokens_matches_prompt_plus_completion() -> None:
    cost = accumulate_cost(
        [{"stage": "entities", "calls": 2, "prompt_tokens": 100, "completion_tokens": 40}]
    )
    d = cost.as_dict()
    assert d["total_tokens"] == d["prompt_tokens"] + d["completion_tokens"]
    assert d["per_stage"] == {"entities": 140}
    # as_dict returns a copy of per_stage, not the internal mapping.
    d["per_stage"]["entities"] = 0
    assert cost.per_stage["entities"] == 140


def test_buildcost_is_frozen() -> None:
    cost = BuildCost(0, 0, 0, 0, {})
    try:
        cost.total_calls = 5  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("BuildCost should be frozen")
