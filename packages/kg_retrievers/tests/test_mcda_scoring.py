"""Tests for weighted MCDA scoring over a TechnologyComparison (§24.13)."""

from __future__ import annotations

from kg_retrievers.mcda_scoring import (
    MCDAResult,
    normalize_criterion,
    score_alternatives,
)


def test_benefit_column_normalizes_max_to_one() -> None:
    """Benefit column {A:10,B:5} → A=1.0, B=0.0."""
    out = normalize_criterion({"A": 10.0, "B": 5.0}, benefit=True)
    assert out == {"A": 1.0, "B": 0.0}


def test_cost_column_inverts_orientation() -> None:
    """Cost direction {A:10,B:5} → A=0.0, B=1.0 (cheaper is better)."""
    out = normalize_criterion({"A": 10.0, "B": 5.0}, benefit=False)
    assert out == {"A": 0.0, "B": 1.0}


def test_all_equal_column_maps_to_one() -> None:
    """All-equal column {A:3,B:3} → both 1.0, benefit or cost."""
    assert normalize_criterion({"A": 3.0, "B": 3.0}, benefit=True) == {"A": 1.0, "B": 1.0}
    assert normalize_criterion({"A": 3.0, "B": 3.0}, benefit=False) == {"A": 1.0, "B": 1.0}


def test_empty_column_returns_empty() -> None:
    """Empty criterion column normalizes to empty dict."""
    assert normalize_criterion({}, benefit=True) == {}


def test_weighted_total_hand_case() -> None:
    """weighted_total == sum(normalized * weight) for a hand-computed case.

    Two criteria: cost (benefit=False) and perf (benefit=True), weights 0.4/0.6.
    Matrix: A={cost:10, perf:100}, B={cost:5, perf:50}.
    Normalized cost:  A=0.0, B=1.0.  Normalized perf: A=1.0, B=0.0.
    A total = 0.0*0.4 + 1.0*0.6 = 0.6 ; B total = 1.0*0.4 + 0.0*0.6 = 0.4.
    """
    matrix = {
        "A": {"cost": 10.0, "perf": 100.0},
        "B": {"cost": 5.0, "perf": 50.0},
    }
    weights = {"cost": 0.4, "perf": 0.6}
    directions = {"cost": False, "perf": True}
    results = score_alternatives(matrix, weights, directions)
    by_id = {r.alternative_id: r for r in results}

    ra = by_id["A"]
    assert ra.normalized_scores == {"cost": 0.0, "perf": 1.0}
    assert ra.weighted_total == sum(ra.normalized_scores[c] * weights[c] for c in weights)
    assert ra.weighted_total == 0.6

    rb = by_id["B"]
    assert rb.weighted_total == 0.4


def test_two_alt_matrix_ranks_correctly() -> None:
    """Two-alternative matrix assigns rank 1 to the higher weighted_total."""
    matrix = {
        "A": {"cost": 10.0, "perf": 100.0},
        "B": {"cost": 5.0, "perf": 50.0},
    }
    weights = {"cost": 0.4, "perf": 0.6}
    directions = {"cost": False, "perf": True}
    results = score_alternatives(matrix, weights, directions)

    assert [r.alternative_id for r in results] == ["A", "B"]
    assert [r.rank for r in results] == [1, 2]
    assert results[0].weighted_total > results[1].weighted_total


def test_tie_broken_by_id_ascending() -> None:
    """A weighted_total tie ranks alternatives by id ascending.

    Symmetric matrix so both alternatives get identical totals: with one benefit
    criterion, {B:10, A:5} normalizes to B=1.0, A=0.0 — not a tie. To force a
    tie use an all-equal criterion so every total is equal (weight * 1.0).
    """
    matrix = {
        "beta": {"score": 7.0},
        "alpha": {"score": 7.0},
    }
    weights = {"score": 1.0}
    directions = {"score": True}
    results = score_alternatives(matrix, weights, directions)

    assert results[0].weighted_total == results[1].weighted_total
    assert [r.alternative_id for r in results] == ["alpha", "beta"]
    assert [r.rank for r in results] == [1, 2]


def test_empty_matrix_returns_empty_list() -> None:
    """Empty matrix → empty result list."""
    assert score_alternatives({}, {"c": 1.0}, {"c": True}) == []


def test_as_dict_normalized_keys_equal_criteria() -> None:
    """as_dict()['normalized_scores'] keys equal the criteria keys."""
    matrix = {
        "A": {"cost": 10.0, "perf": 100.0},
        "B": {"cost": 5.0, "perf": 50.0},
    }
    weights = {"cost": 0.4, "perf": 0.6}
    directions = {"cost": False, "perf": True}
    results = score_alternatives(matrix, weights, directions)

    d = results[0].as_dict()
    assert set(d["normalized_scores"].keys()) == {"cost", "perf"}
    assert set(d["raw_scores"].keys()) == {"cost", "perf"}
    assert isinstance(results[0], MCDAResult)
    assert d["alternative_id"] == results[0].alternative_id
    assert d["rank"] == 1
