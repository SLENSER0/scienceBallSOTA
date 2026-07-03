"""Tests for rank-correlation statistics (§18.11).

Small hand-checkable cases: перфектная монотонность, обратный порядок и одна
инверсия с известными значениями ρ и τ.
"""

from __future__ import annotations

import pytest

from kg_eval.rank_correlation import (
    RankCorrelation,
    analyze,
    kendall_tau,
    spearman_rho,
)


def test_perfect_monotone_gives_plus_one() -> None:
    # y = 2x is strictly increasing → identical rank order.
    x = [1, 2, 3, 4]
    y = [2, 4, 6, 8]
    assert spearman_rho(x, y) == 1.0
    assert kendall_tau(x, y) == 1.0


def test_reversed_gives_minus_one() -> None:
    x = [1, 2, 3, 4]
    y = [8, 6, 4, 2]
    assert spearman_rho(x, y) == -1.0
    assert kendall_tau(x, y) == -1.0


def test_single_inversion_kendall_tau() -> None:
    # Pairs (1,2),(1,3),(2,3): first two concordant, last discordant.
    x = [1, 2, 3]
    y = [1, 3, 2]
    assert round(kendall_tau(x, y), 4) == 0.3333


def test_single_inversion_spearman_rho() -> None:
    x = [1, 2, 3]
    y = [1, 3, 2]
    assert spearman_rho(x, y) == 0.5


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        spearman_rho([1, 2, 3], [1, 2])


def test_n_less_than_two_raises() -> None:
    with pytest.raises(ValueError):
        analyze([1], [1])


def test_as_dict_reports_n() -> None:
    result = analyze([1, 2, 3], [1, 3, 2])
    assert isinstance(result, RankCorrelation)
    d = result.as_dict()
    assert d["n"] == 3
    assert d["spearman_rho"] == 0.5
    assert d["kendall_tau"] == 0.3333
