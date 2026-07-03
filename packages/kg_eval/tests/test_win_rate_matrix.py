"""Tests for pairwise system win-rate ranking (§18.11).

Small hand-checkable head-to-head cases: доля побед, ничьи, разворот при
``higher_is_better=False`` и валидация входа.
"""

from __future__ import annotations

import pytest

from kg_eval.win_rate_matrix import SystemRank, WinRateReport, win_rate_matrix


def test_matrix_fractions() -> None:
    # q0,q1: A beats B; q2: B beats A → A wins 2/3, B wins 1/3.
    report = win_rate_matrix({"A": [1, 1, 0], "B": [0, 0, 1]})
    assert round(report.matrix["A"]["B"], 4) == 0.6667
    assert round(report.matrix["B"]["A"], 4) == 0.3333


def test_ranking_puts_stronger_system_first() -> None:
    report = win_rate_matrix({"A": [1, 1, 0], "B": [0, 0, 1]})
    assert report.ranking[0].name == "A"


def test_aggregate_win_loss_tie_counts() -> None:
    report = win_rate_matrix({"A": [1, 1, 0], "B": [0, 0, 1]})
    a_rank = next(r for r in report.ranking if r.name == "A")
    assert a_rank.wins == 2
    assert a_rank.losses == 1
    assert a_rank.ties == 0


def test_tie_excluded_from_win_fraction() -> None:
    # q0 tie, q1 A beats B → A wins on 1 of 2 questions → 0.5.
    report = win_rate_matrix({"A": [1, 1], "B": [1, 0]})
    assert report.matrix["A"]["B"] == 0.5
    a_rank = next(r for r in report.ranking if r.name == "A")
    assert a_rank.wins == 1
    assert a_rank.ties == 1
    assert a_rank.losses == 0


def test_higher_is_better_false_flips_winner() -> None:
    report = win_rate_matrix({"A": [1, 1, 0], "B": [0, 0, 1]}, higher_is_better=False)
    assert report.ranking[0].name == "B"
    assert round(report.matrix["B"]["A"], 4) == 0.6667


def test_unequal_lengths_raise() -> None:
    with pytest.raises(ValueError):
        win_rate_matrix({"A": [1, 0, 1], "B": [0, 1]})


def test_fewer_than_two_systems_raise() -> None:
    with pytest.raises(ValueError):
        win_rate_matrix({"A": [1, 0, 1]})


def test_as_dict_reports_question_count() -> None:
    report = win_rate_matrix({"A": [1, 1, 0], "B": [0, 0, 1]})
    assert isinstance(report, WinRateReport)
    d = report.as_dict()
    assert d["n_questions"] == 3
    assert d["matrix"]["A"]["B"] == 0.6667
    ranking = d["ranking"]
    assert isinstance(ranking, list)
    assert ranking[0]["name"] == "A"


def test_system_rank_as_dict_roundtrips_fields() -> None:
    rank = SystemRank(name="A", mean_win_rate=0.66666, wins=2, losses=1, ties=0)
    assert rank.as_dict() == {
        "name": "A",
        "mean_win_rate": 0.6667,
        "wins": 2,
        "losses": 1,
        "ties": 0,
    }
