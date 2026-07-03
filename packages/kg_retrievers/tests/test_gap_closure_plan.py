"""Tests for §15.9/§23 greedy gap-closure planning (pure python, no store).

RU: Проверяем жадный set-cover: покрытие, порядок выбора, лимит экспериментов,
влияние весов, непокрываемые пробелы, суммарную стоимость и round-trip as_dict().
EN: Exercises the greedy set-cover: coverage, selection order, experiment cap,
weight influence, un-closable gaps, total cost and the as_dict() round-trip.
"""

from __future__ import annotations

import pytest

from kg_retrievers.gap_closure_plan import ClosurePlan, plan_closures

GAPS3 = ["g1", "g2", "g3"]


def test_single_experiment_covers_all() -> None:
    """(1) One experiment closing all 3 gaps -> chosen len 1, coverage_ratio 1.0."""
    cands = [{"experiment_id": "E", "closes": ["g1", "g2", "g3"], "cost": 1.0}]
    plan = plan_closures(GAPS3, cands)
    assert plan.chosen == ["E"]
    assert len(plan.chosen) == 1
    assert plan.coverage_ratio == 1.0
    assert sorted(plan.closed_gap_ids) == ["g1", "g2", "g3"]
    assert plan.uncovered_gap_ids == []


def test_greedy_picks_a_then_b() -> None:
    """(2) A={g1,g2} c1, B={g2,g3} c1 -> greedy picks A then B, all 3 closed."""
    cands = [
        {"experiment_id": "A", "closes": ["g1", "g2"], "cost": 1.0},
        {"experiment_id": "B", "closes": ["g2", "g3"], "cost": 1.0},
    ]
    plan = plan_closures(GAPS3, cands)
    # A and B tie on gained/cost (2/1 each) but A < B lexicographically -> A first.
    assert plan.chosen == ["A", "B"]
    assert len(plan.closed_gap_ids) == 3
    assert sorted(plan.closed_gap_ids) == ["g1", "g2", "g3"]
    assert plan.uncovered_gap_ids == []
    assert plan.coverage_ratio == 1.0


def test_max_experiments_leaves_gap_uncovered() -> None:
    """(3) max_experiments=1 leaves an un-closable gap uncovered, ratio < 1.0."""
    cands = [
        {"experiment_id": "A", "closes": ["g1", "g2"], "cost": 1.0},
        {"experiment_id": "B", "closes": ["g3"], "cost": 1.0},
    ]
    plan = plan_closures(GAPS3, cands, max_experiments=1)
    assert plan.chosen == ["A"]  # A covers 2, B covers 1 -> A wins the single slot
    assert plan.uncovered_gap_ids == ["g3"]
    assert plan.coverage_ratio < 1.0
    assert plan.coverage_ratio == pytest.approx(2.0 / 3.0)


def test_weights_make_high_weight_gap_outrank_two_low() -> None:
    """(4) Weights let a single heavy gap outrank two light ones in a tie."""
    cands = [
        {"experiment_id": "X", "closes": ["g1"], "cost": 1.0},
        {"experiment_id": "Y", "closes": ["g2", "g3"], "cost": 1.0},
    ]
    # Unweighted: Y (covers 2) beats X (covers 1).
    unweighted = plan_closures(GAPS3, cands)
    assert unweighted.chosen[0] == "Y"
    # Weighted: g1 is heavy (10) so X (gain 10) beats Y (gain 2) and is picked first.
    weighted = plan_closures(GAPS3, cands, weights={"g1": 10.0, "g2": 1.0, "g3": 1.0})
    assert weighted.chosen[0] == "X"


def test_gap_no_candidate_closes_stays_uncovered() -> None:
    """(5) A gap no candidate closes remains in uncovered_gap_ids."""
    cands = [{"experiment_id": "A", "closes": ["g1", "g2"], "cost": 1.0}]
    plan = plan_closures(GAPS3, cands)
    assert plan.chosen == ["A"]
    assert plan.uncovered_gap_ids == ["g3"]
    assert sorted(plan.closed_gap_ids) == ["g1", "g2"]
    assert plan.coverage_ratio == pytest.approx(2.0 / 3.0)


def test_total_cost_sums_chosen_costs() -> None:
    """(6) total_cost equals the sum of chosen candidate costs."""
    cands = [
        {"experiment_id": "A", "closes": ["g1"], "cost": 2.5},
        {"experiment_id": "B", "closes": ["g2"], "cost": 1.5},
        {"experiment_id": "C", "closes": ["g3"], "cost": 3.0},
    ]
    plan = plan_closures(GAPS3, cands)
    assert sorted(plan.chosen) == ["A", "B", "C"]
    assert plan.total_cost == pytest.approx(2.5 + 1.5 + 3.0)


def test_empty_candidates_leaves_all_uncovered() -> None:
    """(7) Empty candidates -> chosen [], uncovered == all gap ids, ratio 0.0."""
    plan = plan_closures(GAPS3, [])
    assert plan.chosen == []
    assert plan.closed_gap_ids == []
    assert plan.uncovered_gap_ids == GAPS3
    assert plan.total_cost == 0.0
    assert plan.coverage_ratio == 0.0


def test_as_dict_round_trips_and_ratio_bounded() -> None:
    """(8) as_dict() round-trips through ClosurePlan and ratio stays in [0, 1]."""
    cands = [
        {"experiment_id": "A", "closes": ["g1", "g2"], "cost": 1.0},
        {"experiment_id": "B", "closes": ["g3"], "cost": 1.0},
    ]
    plan = plan_closures(GAPS3, cands)
    d = plan.as_dict()
    assert set(d) == {
        "chosen",
        "closed_gap_ids",
        "uncovered_gap_ids",
        "total_cost",
        "coverage_ratio",
    }
    assert 0.0 <= d["coverage_ratio"] <= 1.0
    rebuilt = ClosurePlan(**d)
    assert rebuilt == plan
    assert rebuilt.as_dict() == d


# --- extra hand-checkable edge cases -----------------------------------------


def test_lower_cost_wins_tie_on_ratio() -> None:
    """Ties on gained weight break toward the lower-cost experiment (§15.9)."""
    cands = [
        {"experiment_id": "Z", "closes": ["g1", "g2"], "cost": 1.0},
        {"experiment_id": "W", "closes": ["g1", "g2", "g3"], "cost": 2.0},
    ]
    # Z: 2/1 = 2.0 ratio; W: 3/2 = 1.5 ratio -> Z picked first, then W adds g3.
    plan = plan_closures(GAPS3, cands)
    assert plan.chosen == ["Z", "W"]
    assert sorted(plan.closed_gap_ids) == ["g1", "g2", "g3"]


def test_dict_gaps_with_inline_weights() -> None:
    """Gap dicts may carry inline weights; explicit weights arg overrides them."""
    gaps = [
        {"gap_id": "g1", "weight": 5.0},
        {"gap_id": "g2", "weight": 1.0},
        {"gap_id": "g3", "weight": 1.0},
    ]
    cands = [
        {"experiment_id": "X", "closes": ["g1"], "cost": 1.0},
        {"experiment_id": "Y", "closes": ["g2", "g3"], "cost": 1.0},
    ]
    plan = plan_closures(gaps, cands)
    assert plan.chosen[0] == "X"  # inline weight 5 beats Y's gain of 2


def test_redundant_candidate_not_chosen() -> None:
    """A candidate adding no new gap is never selected (§15.9)."""
    cands = [
        {"experiment_id": "A", "closes": ["g1", "g2", "g3"], "cost": 1.0},
        {"experiment_id": "B", "closes": ["g1", "g2"], "cost": 1.0},
    ]
    plan = plan_closures(GAPS3, cands)
    assert plan.chosen == ["A"]
    assert "B" not in plan.chosen


def test_zero_gaps_full_coverage() -> None:
    """No open gaps -> nothing chosen and coverage_ratio defaults to 1.0."""
    plan = plan_closures([], [{"experiment_id": "A", "closes": ["x"], "cost": 1.0}])
    assert plan.chosen == []
    assert plan.uncovered_gap_ids == []
    assert plan.coverage_ratio == 1.0


def test_default_cost_is_one() -> None:
    """A candidate without an explicit cost defaults to cost 1.0 (§15.9)."""
    plan = plan_closures(["g1"], [{"experiment_id": "A", "closes": ["g1"]}])
    assert plan.chosen == ["A"]
    assert plan.total_cost == pytest.approx(1.0)


def test_invalid_cost_rejected() -> None:
    """A non-positive cost is rejected with ValueError."""
    with pytest.raises(ValueError):
        plan_closures(["g1"], [{"experiment_id": "A", "closes": ["g1"], "cost": 0.0}])


def test_negative_max_experiments_rejected() -> None:
    """A negative max_experiments is rejected with ValueError."""
    with pytest.raises(ValueError):
        plan_closures(GAPS3, [], max_experiments=-1)
