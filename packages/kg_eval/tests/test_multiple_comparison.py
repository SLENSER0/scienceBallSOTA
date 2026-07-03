"""Tests for multiple-comparison correction (§23.31).

Hand-checkable Holm-Bonferroni and Benjamini-Hochberg corrections over small
p-value families with fully worked expected values.
"""

from __future__ import annotations

from kg_eval.multiple_comparison import (
    CorrectedResult,
    CorrectionReport,
    benjamini_hochberg,
    holm_bonferroni,
)


def _by_name(report: CorrectionReport) -> dict[str, CorrectedResult]:
    return {r.name: r for r in report.results}


def test_holm_marks_a_significant_and_b_not() -> None:
    # Sorted ascending: a=0.01, c=0.03, b=0.04 (n=3).
    #   a: 3*0.01 = 0.03            -> significant (<= 0.05)
    #   c: max(0.03, 2*0.03=0.06)   -> 0.06 not significant
    #   b: max(0.06, 1*0.04=0.04)   -> 0.06 not significant (step-down gap)
    report = holm_bonferroni({"a": 0.01, "b": 0.04, "c": 0.03}, alpha=0.05)
    res = _by_name(report)
    assert res["a"].significant is True
    assert res["a"].adjusted_p == 0.03
    assert res["b"].significant is False
    assert res["b"].adjusted_p == 0.06
    assert res["c"].significant is False
    assert report.n == 3
    assert report.n_significant == 1
    assert report.method == "holm-bonferroni"


def test_holm_single_pvalue_stays_significant() -> None:
    report = holm_bonferroni({"only": 0.01}, alpha=0.05)
    res = _by_name(report)
    assert res["only"].adjusted_p == 0.01
    assert res["only"].significant is True
    assert report.n == 1
    assert report.n_significant == 1


def test_holm_all_high_pvalues_none_significant() -> None:
    report = holm_bonferroni({"a": 0.9, "b": 0.9, "c": 0.9}, alpha=0.05)
    assert report.n_significant == 0
    assert all(not r.significant for r in report.results)


def test_adjusted_p_clamped_to_one() -> None:
    # 3 * 0.9 = 2.7 must clamp to 1.0.
    report = holm_bonferroni({"a": 0.9, "b": 0.9, "c": 0.9}, alpha=0.05)
    assert all(r.adjusted_p <= 1.0 for r in report.results)
    assert max(r.adjusted_p for r in report.results) == 1.0


def test_bh_at_least_as_lenient_as_holm() -> None:
    pvals = {"a": 0.01, "b": 0.04, "c": 0.03}
    holm = holm_bonferroni(pvals, alpha=0.05)
    bh = benjamini_hochberg(pvals, alpha=0.05)
    assert bh.n_significant >= holm.n_significant
    # Concretely: BH marks all three significant here (0.03, 0.04, 0.04).
    assert bh.n_significant == 3
    assert holm.n_significant == 1


def test_bh_adjusted_values_hand_checked() -> None:
    # Sorted: a=0.01, c=0.03, b=0.04 (n=3), step-up min sweep:
    #   b (rank 3): 0.04*3/3 = 0.04
    #   c (rank 2): min(0.04, 0.03*3/2=0.045) = 0.04
    #   a (rank 1): min(0.04, 0.01*3/1=0.03)  = 0.03
    bh = benjamini_hochberg({"a": 0.01, "b": 0.04, "c": 0.03}, alpha=0.05)
    res = _by_name(bh)
    assert res["a"].adjusted_p == 0.03
    assert res["c"].adjusted_p == 0.04
    assert res["b"].adjusted_p == 0.04
    assert all(r.significant for r in bh.results)
    assert bh.method == "benjamini-hochberg"


def test_results_preserve_one_entry_per_key_in_input_order() -> None:
    pvals = {"b": 0.04, "a": 0.01, "c": 0.03}
    report = holm_bonferroni(pvals, alpha=0.05)
    assert tuple(r.name for r in report.results) == ("b", "a", "c")
    assert len(report.results) == len(pvals)


def test_empty_pvals() -> None:
    for report in (holm_bonferroni({}), benjamini_hochberg({})):
        assert report.n == 0
        assert report.n_significant == 0
        assert report.results == ()


def test_as_dict_shapes() -> None:
    report = holm_bonferroni({"a": 0.01, "b": 0.04}, alpha=0.05)
    d = report.as_dict()
    assert d["method"] == "holm-bonferroni"
    assert d["alpha"] == 0.05
    assert d["n"] == 2
    assert isinstance(d["results"], list)
    first = d["results"][0]
    assert set(first) == {"name", "p_value", "adjusted_p", "significant"}


def test_bh_all_high_none_significant() -> None:
    report = benjamini_hochberg({"a": 0.8, "b": 0.9}, alpha=0.05)
    assert report.n_significant == 0
    assert all(r.adjusted_p <= 1.0 for r in report.results)
