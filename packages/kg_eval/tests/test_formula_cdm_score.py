"""Tests for formula CDM-lite multiset scoring — тесты (§23.34/§23.31)."""

from __future__ import annotations

from kg_eval.formula_cdm_score import FormulaCDM, score_formula, tokenize


def test_tokenize_latex_command_is_one_token() -> None:
    # \alpha is a single atom; the rest split per character.
    assert tokenize("\\alpha + 1") == ("\\alpha", "+", "1")


def test_tokenize_strips_and_ignores_internal_whitespace() -> None:
    assert tokenize("  x ^ 2  ") == ("x", "^", "2")


def test_tokenize_structural_and_digit_atoms() -> None:
    assert tokenize("x^{12}") == ("x", "^", "{", "1", "2", "}")


def test_identical_formulas_are_perfect() -> None:
    r = score_formula("\\frac{a}{b}", "\\frac{a}{b}")
    assert r.precision == 1.0
    assert r.recall == 1.0
    assert r.f1 == 1.0


def test_matched_equals_token_count_for_identical() -> None:
    r = score_formula("x^2+1", "x^2+1")
    assert r.n_gold == r.n_pred == 5  # x ^ 2 + 1
    assert r.matched == 5


def test_multiplicity_lowers_recall() -> None:
    # gold has 'x' twice, pred once -> only one overlaps.
    r = score_formula("x+x", "x")
    assert r.n_gold == 3  # x + x
    assert r.n_pred == 1
    assert r.matched == 1
    assert r.recall < 1.0
    assert r.recall == 1 / 3


def test_disjoint_token_sets_score_zero() -> None:
    r = score_formula("a+b", "c*d")
    assert r.matched == 0
    assert r.f1 == 0.0


def test_spurious_pred_tokens_lower_precision_keep_recall() -> None:
    # pred contains all gold tokens plus an extra one.
    r = score_formula("a+b", "a+b+c")
    assert r.recall == 1.0
    assert r.precision < 1.0
    assert r.matched == 3  # a + b
    assert r.n_pred == 5  # a + b + c


def test_both_empty_is_perfect() -> None:
    r = score_formula("", "")
    assert r.n_gold == 0
    assert r.n_pred == 0
    assert r.f1 == 1.0
    assert r.precision == 1.0
    assert r.recall == 1.0


def test_gold_empty_pred_nonempty_scores_zero() -> None:
    r = score_formula("", "x+1")
    assert r.precision == 0.0
    assert r.f1 == 0.0


def test_pred_empty_gold_nonempty_scores_zero() -> None:
    r = score_formula("x+1", "")
    assert r.recall == 0.0
    assert r.f1 == 0.0


def test_as_dict_rounds_two_thirds() -> None:
    # gold 4 distinct atoms, pred those 4 plus 4 spurious -> matched 4.
    # precision = 4/8 = 0.5, recall = 4/4 = 1.0, f1 = 2*0.5*1/(1.5) = 2/3.
    r = score_formula("abcd", "abcdefgh")
    assert r.matched == 4
    assert r.precision == 0.5
    assert r.recall == 1.0
    assert r.f1 == 2 / 3
    d = r.as_dict()
    assert d["f1"] == 0.666667


def test_as_dict_shape_and_types() -> None:
    r = score_formula("a", "a")
    d = r.as_dict()
    assert d == {
        "n_gold": 1,
        "n_pred": 1,
        "matched": 1,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    assert isinstance(r, FormulaCDM)
