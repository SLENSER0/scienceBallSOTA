"""Tests for GraphRAG map-step candidate selection under a token budget (§11.7)."""

from __future__ import annotations

import json

from kg_retrievers.graphrag_map_candidate_selector import (
    MapSelection,
    select_candidates,
)


def _report(community_id: str, score: float, est_tokens: int) -> dict:
    return {"community_id": community_id, "score": score, "est_tokens": est_tokens}


def test_max_reports_caps_to_top_two() -> None:
    reports = [
        _report("c1", 0.9, 100),
        _report("c2", 0.5, 100),
        _report("c3", 0.7, 100),
    ]
    sel = select_candidates(reports, token_budget=10_000, max_reports=2)
    # Budget is huge, so only max_reports matters: the two highest scores are c1, c3.
    assert sel.selected == ("c1", "c3")
    assert sel.skipped == ("c2",)


def test_over_budget_item_skipped_smaller_next_taken() -> None:
    reports = [
        _report("big", 0.9, 100),
        _report("small", 0.8, 10),
    ]
    # Budget 50: "big" (100) overflows and is skipped, walk continues, "small" (10) fits.
    sel = select_candidates(reports, token_budget=50, max_reports=10)
    assert sel.selected == ("small",)
    assert sel.skipped == ("big",)
    assert sel.used_tokens == 10


def test_used_tokens_is_sum_of_selected_and_within_budget() -> None:
    reports = [
        _report("a", 0.9, 30),
        _report("b", 0.8, 40),
        _report("c", 0.7, 25),
    ]
    sel = select_candidates(reports, token_budget=100, max_reports=10)
    assert sel.selected == ("a", "b", "c")
    assert sel.used_tokens == 30 + 40 + 25
    assert sel.used_tokens <= sel.budget


def test_ties_broken_by_community_id_ascending() -> None:
    reports = [
        _report("z", 0.5, 10),
        _report("a", 0.5, 10),
        _report("m", 0.5, 10),
    ]
    sel = select_candidates(reports, token_budget=10, max_reports=1)
    # All tie on score; "a" wins the tie-break, so it is the single selected id.
    assert sel.selected == ("a",)
    assert sel.skipped == ("m", "z")


def test_empty_reports_yields_nothing() -> None:
    sel = select_candidates([], token_budget=1000, max_reports=5)
    assert sel.selected == ()
    assert sel.skipped == ()
    assert sel.used_tokens == 0


def test_every_id_appears_exactly_once() -> None:
    reports = [
        _report("a", 0.9, 60),
        _report("b", 0.8, 60),
        _report("c", 0.7, 60),
        _report("d", 0.6, 60),
    ]
    sel = select_candidates(reports, token_budget=120, max_reports=10)
    all_ids = set(sel.selected) | set(sel.skipped)
    assert all_ids == {"a", "b", "c", "d"}
    assert len(sel.selected) + len(sel.skipped) == 4
    assert set(sel.selected).isdisjoint(sel.skipped)


def test_as_dict_budget_and_json_round_trip() -> None:
    reports = [_report("a", 0.9, 30), _report("b", 0.8, 40)]
    sel = select_candidates(reports, token_budget=100, max_reports=5)
    payload = sel.as_dict()
    assert payload["budget"] == 100
    restored = json.loads(json.dumps(payload))
    assert restored == payload


def test_frozen_dataclass_construct_directly() -> None:
    sel = MapSelection(selected=("a",), skipped=("b",), used_tokens=30, budget=100)
    assert sel.used_tokens == 30
    assert sel.budget == 100
