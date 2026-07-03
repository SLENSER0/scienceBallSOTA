"""Hand-checkable tests for Fleiss' kappa multi-annotator agreement (§18.6)."""

from __future__ import annotations

import pytest

from kg_eval.fleiss_kappa import FleissReport, fleiss_kappa

# Perfect agreement: 3 raters, item1 all A, item2 all B.
#   P_i = (3² − 3) / (3·2) = 6/6 = 1 for each item → P̄ = 1.
#   p_A = p_B = 3/6 = 0.5 → P_e = 0.25 + 0.25 = 0.5.
#   kappa = (1 − 0.5) / (1 − 0.5) = 1.
PERFECT = [{"A": 3, "B": 0}, {"A": 0, "B": 3}]

# Split votes: item1 = 2A/1B, item2 = 1A/2B (3 raters).
#   P_i = (2² + 1² − 3) / 6 = (5 − 3)/6 = 1/3 for each → P̄ = 1/3.
#   p_A = p_B = 3/6 = 0.5 → P_e = 0.5.
#   kappa = (1/3 − 1/2) / (1 − 1/2) = (−1/6) / (1/2) = −1/3.
SPLIT = [{"A": 2, "B": 1}, {"A": 1, "B": 2}]


def test_perfect_agreement_p_bar_p_e_kappa() -> None:
    r = fleiss_kappa(PERFECT)
    assert r.p_bar == pytest.approx(1.0)
    assert r.p_e == pytest.approx(0.5)
    assert r.kappa == pytest.approx(1.0)


def test_split_votes_negative_kappa() -> None:
    r = fleiss_kappa(SPLIT)
    assert r.p_bar == pytest.approx(0.3333, abs=1e-4)
    assert r.p_e == pytest.approx(0.5)
    assert r.kappa == pytest.approx(-0.3333, abs=1e-4)


def test_n_raters_and_n_items() -> None:
    r = fleiss_kappa(PERFECT)
    assert r.n_raters == 3
    assert r.n_items == 2


def test_categories_sorted_tuple() -> None:
    r = fleiss_kappa([{"B": 1, "A": 2}, {"A": 1, "B": 2}])
    assert r.categories == ("A", "B")


def test_ragged_rater_totals_raise() -> None:
    with pytest.raises(ValueError, match="ragged"):
        fleiss_kappa([{"A": 3, "B": 0}, {"A": 1, "B": 3}])


def test_single_item_raises() -> None:
    with pytest.raises(ValueError, match=">=2 items"):
        fleiss_kappa([{"A": 3}])


def test_as_dict_kappa_perfect() -> None:
    d = fleiss_kappa(PERFECT).as_dict()
    assert d["kappa"] == 1.0
    assert isinstance(fleiss_kappa(PERFECT), FleissReport)
