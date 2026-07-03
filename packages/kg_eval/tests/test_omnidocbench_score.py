"""OmniDocBench end-to-end parse scoring — тесты сквозной оценки (§23.34).

Hand-checkable: every fixture's expected component and weighted-overall scores
are computed by hand in the assertion, no golden files (OmniDocBench,
arXiv:2412.07626).
"""

from __future__ import annotations

import pytest

import kg_eval.omnidocbench_score as mod
from kg_eval.omnidocbench_score import OmniDocScore, ParsedDoc, omnidoc_score


def _doc() -> ParsedDoc:
    """A fully-populated reference document with all three components."""
    return ParsedDoc(
        text="the quick brown fox",
        table=[["a", "b"], ["c", "d"]],
        formula="E=mc^2",
    )


def test_identical_doc_overall_one() -> None:
    """Identical populated doc: every component 1.0, overall 1.0 (§23.34)."""
    gold = _doc()
    pred = _doc()
    s = omnidoc_score(gold, pred)
    assert s.text_score == 1.0
    assert s.table_score == 1.0
    assert s.formula_score == 1.0
    assert s.edit_distance == 0.0
    assert s.overall == pytest.approx(1.0)


def test_text_edits_lower_text_score() -> None:
    """Text edits drop text_score below 1.0 and raise edit_distance (§23.34)."""
    # "abcd" -> "abxd": one substitution, similarity 1 - 1/4 = 0.75.
    gold = ParsedDoc(text="abcd", table=[["a"]], formula="x")
    pred = ParsedDoc(text="abxd", table=[["a"]], formula="x")
    s = omnidoc_score(gold, pred)
    assert s.text_score == 0.75
    assert s.edit_distance == 0.25
    assert s.table_score == 1.0
    assert s.formula_score == 1.0
    assert s.overall < 1.0


def test_table_mismatch_lowers_table_score() -> None:
    """A wrong table cell lowers table_score below 1.0 (§23.34)."""
    # 2x2 gold, one of four cells wrong: structure 1.0, content 0.75 -> 0.875.
    gold = ParsedDoc(text="same", table=[["a", "b"], ["c", "d"]])
    pred = ParsedDoc(text="same", table=[["a", "b"], ["c", "X"]])
    s = omnidoc_score(gold, pred)
    assert s.text_score == 1.0
    assert s.table_score == pytest.approx(0.875)
    assert s.overall < 1.0


def test_formula_mismatch_zero() -> None:
    """A differing formula scores 0.0 while text/table stay perfect (§23.34)."""
    gold = ParsedDoc(text="same", table=[["a"]], formula="E=mc^2")
    pred = ParsedDoc(text="same", table=[["a"]], formula="E=mc^3")
    s = omnidoc_score(gold, pred)
    assert s.formula_score == 0.0
    assert s.text_score == 1.0
    assert s.table_score == 1.0
    # overall = 0.5*1 + 0.3*1 + 0.2*0 = 0.8.
    assert s.overall == pytest.approx(0.8)


def test_formula_exact_match_whitespace_insensitive() -> None:
    """Formulas matching only after whitespace folding still score 1.0 (§23.34)."""
    gold = ParsedDoc(formula="E = m c^2")
    pred = ParsedDoc(formula="  E =  m   c^2 ")
    s = omnidoc_score(gold, pred)
    assert s.formula_score == 1.0


def test_weighted_overall_hand_checked() -> None:
    """Weighted overall = 0.5*0.75 + 0.3*0.875 + 0.2*1.0 = 0.8375 (§23.34)."""
    gold = ParsedDoc(
        text="abcd",
        table=[["a", "b"], ["c", "d"]],
        formula="E=mc^2",
    )
    pred = ParsedDoc(
        text="abxd",  # similarity 0.75
        table=[["a", "b"], ["c", "X"]],  # TEDS 0.5*(1.0 + 0.75) = 0.875
        formula="E=mc^2",  # exact match 1.0
    )
    s = omnidoc_score(gold, pred)
    assert s.text_score == 0.75
    assert s.table_score == pytest.approx(0.875)
    assert s.formula_score == 1.0
    assert s.overall == pytest.approx(0.5 * 0.75 + 0.3 * 0.875 + 0.2 * 1.0)
    assert s.overall == pytest.approx(0.8375)


def test_empty_gold_and_empty_pred_overall_one() -> None:
    """Two empty documents are a vacuous perfect match -> overall 1.0 (§23.34)."""
    s = omnidoc_score(ParsedDoc(), ParsedDoc())
    assert s.text_score == 1.0
    assert s.table_score == 1.0  # both tables absent -> nothing to get wrong
    assert s.formula_score == 1.0  # '' == ''
    assert s.overall == pytest.approx(1.0)
    assert s.edit_distance == 0.0


def test_empty_gold_populated_pred_scores_low() -> None:
    """Empty gold vs a populated prediction scores every component 0.0 (§23.34)."""
    pred = ParsedDoc(text="spurious", table=[["x"]], formula="y")
    s = omnidoc_score(ParsedDoc(), pred)
    assert s.text_score == 0.0  # similarity 1 - len/len = 0.0
    assert s.table_score == 0.0  # gold absent but pred present
    assert s.formula_score == 0.0  # '' != 'y'
    assert s.overall == pytest.approx(0.0)
    assert s.edit_distance == 1.0


def test_as_dict_stable_keys() -> None:
    """as_dict() exposes the five frozen fields with stable keys (§23.34)."""
    s = omnidoc_score(_doc(), _doc())
    d = s.as_dict()
    assert set(d) == {
        "text_score",
        "table_score",
        "formula_score",
        "overall",
        "edit_distance",
    }
    assert isinstance(s, OmniDocScore)


def test_frozen_dataclass_immutable() -> None:
    """OmniDocScore is frozen — assignment raises (§23.34)."""
    s = omnidoc_score(_doc(), _doc())
    with pytest.raises((AttributeError, TypeError)):
        s.overall = 0.0  # type: ignore[misc]


def test_docstring_cites_arxiv_id() -> None:
    """Module docstring cites the OmniDocBench paper arXiv id (hard rule)."""
    assert mod.__doc__ is not None
    assert "2412.07626" in mod.__doc__
