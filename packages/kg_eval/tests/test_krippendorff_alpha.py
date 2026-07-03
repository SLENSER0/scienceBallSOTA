"""Tests for Krippendorff's alpha (nominal) над золотым набором (§18.6)."""

from __future__ import annotations

import pytest

from kg_eval.krippendorff_alpha import AlphaReport, krippendorff_alpha_nominal


def test_perfect_agreement_alpha_one() -> None:
    # Case 1: two coders both label [a, a, b, b] → no disagreement → alpha == 1.0.
    data = {"c1": ["a", "a", "b", "b"], "c2": ["a", "a", "b", "b"]}
    rep = krippendorff_alpha_nominal(data)
    assert rep.alpha == 1.0
    assert rep.d_observed == 0.0
    assert rep.n_units == 4
    assert rep.n_pairable == 8


def test_canonical_six_unit_example() -> None:
    # Case 2 + 3: u1..u6 = (1,1),(2,2),(3,3),(3,3),(2,2),(1,2).
    data = {
        "c1": [1, 2, 3, 3, 2, 1],
        "c2": [1, 2, 3, 3, 2, 2],
    }
    rep = krippendorff_alpha_nominal(data)
    assert round(rep.d_observed, 4) == 0.1667
    assert round(rep.d_expected, 4) == 0.7121
    assert round(rep.alpha, 3) == 0.766
    assert rep.n_pairable == 12  # case 3
    assert rep.n_units == 6


def test_perfect_disagreement_negative_alpha() -> None:
    # Case 4: coders systematically swap two values → alpha < 0.0 (here −0.5).
    data = {"c1": ["a", "b"], "c2": ["b", "a"]}
    rep = krippendorff_alpha_nominal(data)
    assert rep.alpha < 0.0
    assert rep.alpha == pytest.approx(-0.5)


def test_none_values_excluded_from_pairable() -> None:
    # Case 5: None is missing → dropped from present values / n_pairable.
    # Units: u0=(a,a) pairable(2); u1=(b,None)->1 present, dropped; u2=(c,c) pairable(2).
    data = {"c1": ["a", "b", "c"], "c2": ["a", None, "c"]}
    rep = krippendorff_alpha_nominal(data)
    assert rep.n_units == 3
    assert rep.n_pairable == 4  # only u0 and u2 contribute (2 + 2)
    assert rep.alpha == 1.0


def test_no_pairable_data_raises() -> None:
    # Case 6: a single coder → every unit has one present value → nothing pairable.
    with pytest.raises(ValueError):
        krippendorff_alpha_nominal({"only": ["a", "b", "c"]})


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        krippendorff_alpha_nominal({})


def test_as_dict_roundtrip() -> None:
    # Case 7: as_dict() exposes rounded fields with alpha == 1.0 for the perfect case.
    data = {"c1": ["a", "a", "b", "b"], "c2": ["a", "a", "b", "b"]}
    rep = krippendorff_alpha_nominal(data)
    assert isinstance(rep, AlphaReport)
    d = rep.as_dict()
    assert d["alpha"] == 1.0
    assert d["n_units"] == 4
    assert d["n_pairable"] == 8
    assert d["d_observed"] == 0.0


def test_ragged_sequences_raise() -> None:
    with pytest.raises(ValueError):
        krippendorff_alpha_nominal({"c1": ["a", "b"], "c2": ["a"]})
