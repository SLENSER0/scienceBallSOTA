"""Hand-checkable tests for the coverage-matrix cell-accuracy eval (§15.5/§18.7)."""

from __future__ import annotations

from kg_eval.coverage_matrix_eval import (
    CoverageCellScore,
    _cell_key,
    evaluate_coverage,
)


def _cell(mat: str, prop: str, has_gap: bool, regime: str | None = None) -> dict:
    """Build one coverage cell dict."""
    cell: dict = {"material_id": mat, "property_id": prop, "has_gap": has_gap}
    if regime is not None:
        cell["regime_id"] = regime
    return cell


def test_cell_key_includes_regime_only_when_present() -> None:
    """_cell_key drops regime_id when absent so keyed cells stay distinct."""
    assert _cell_key(_cell("m1", "p1", True)) == ("m1", "p1")
    assert _cell_key(_cell("m1", "p1", True, regime="r1")) == ("m1", "p1", "r1")
    # Assertion (5) precondition: a regime-less key differs from a regime-bearing one.
    assert _cell_key(_cell("m1", "p1", True)) != _cell_key(_cell("m1", "p1", True, "r1"))


def test_identical_matrices_score_perfect() -> None:
    """Assertion (1): identical matrices give precision==recall==f1==accuracy==1.0."""
    cells = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", False),
        _cell("m2", "p1", True),
    ]
    score = evaluate_coverage(cells, [dict(c) for c in cells])
    assert score.gap_precision == 1.0
    assert score.gap_recall == 1.0
    assert score.gap_f1 == 1.0
    assert score.cell_accuracy == 1.0
    assert score.n_cells == 3


def test_false_positive_gap_drops_precision_keeps_recall() -> None:
    """Assertion (2): a spurious gap prediction cuts precision but not recall."""
    golden = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", False),
    ]
    predicted = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", True),  # false positive gap
    ]
    score = evaluate_coverage(predicted, golden)
    # tp=1, fp=1 -> precision 0.5; tp=1, fn=0 -> recall 1.0
    assert score.gap_precision == 0.5
    assert score.gap_recall == 1.0
    assert score.gap_precision < 1.0


def test_missed_gap_drops_recall() -> None:
    """Assertion (3): a missed golden gap cuts recall below 1.0."""
    golden = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", True),
    ]
    predicted = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", False),  # missed gap
    ]
    score = evaluate_coverage(predicted, golden)
    # tp=1, fn=1 -> recall 0.5; precision 1.0 (no false positives)
    assert score.gap_recall == 0.5
    assert score.gap_precision == 1.0
    assert score.gap_recall < 1.0


def test_cell_accuracy_counts_covered_and_gap() -> None:
    """Assertion (4): cell_accuracy tallies both covered and gap agreement."""
    golden = [
        _cell("m1", "p1", True),  # gap, matched
        _cell("m1", "p2", False),  # covered, matched
        _cell("m2", "p1", True),  # gap, missed below
        _cell("m2", "p2", False),  # covered, flipped below
    ]
    predicted = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", False),
        _cell("m2", "p1", False),  # gap -> covered (wrong)
        _cell("m2", "p2", True),  # covered -> gap (wrong)
    ]
    score = evaluate_coverage(predicted, golden)
    # 2 of 4 cells agree (one gap match + one covered match).
    assert score.cell_accuracy == 0.5
    assert score.n_cells == 4


def test_golden_only_key_scored_as_predicted_covered() -> None:
    """Assertion (5): a golden-only key counts as predicted covered (FN if gap)."""
    golden = [
        _cell("m1", "p1", True),
        _cell("m2", "p9", True),  # absent from predicted
    ]
    predicted = [
        _cell("m1", "p1", True),
    ]
    score = evaluate_coverage(predicted, golden)
    # missing predicted cell -> covered -> false negative on the golden gap
    assert score.n_cells == 2
    assert score.gap_recall == 0.5  # tp=1, fn=1
    assert score.gap_precision == 1.0
    # the union still scores the missing cell: 1 match (m1/p1), 1 miss (m2/p9)
    assert score.cell_accuracy == 0.5


def test_empty_inputs_all_zero() -> None:
    """Assertion (6): empty inputs give an all-zero score with n_cells 0."""
    score = evaluate_coverage([], [])
    assert score.gap_precision == 0.0
    assert score.gap_recall == 0.0
    assert score.gap_f1 == 0.0
    assert score.cell_accuracy == 0.0
    assert score.n_cells == 0


def test_f1_is_harmonic_mean_of_reported_precision_recall() -> None:
    """Assertion (7): f1 equals the harmonic mean of reported precision/recall."""
    golden = [
        _cell("m1", "p1", True),
        _cell("m1", "p2", True),
        _cell("m1", "p3", False),
    ]
    predicted = [
        _cell("m1", "p1", True),  # tp
        _cell("m1", "p2", False),  # fn
        _cell("m1", "p3", True),  # fp
    ]
    score = evaluate_coverage(predicted, golden)
    p, r = score.gap_precision, score.gap_recall
    expected_f1 = 2 * p * r / (p + r)
    assert score.gap_f1 == expected_f1
    assert score.gap_precision == 0.5  # tp=1, fp=1
    assert score.gap_recall == 0.5  # tp=1, fn=1


def test_as_dict_round_trips_all_five_fields() -> None:
    """Assertion (8): as_dict() carries all five fields with matching values."""
    score = CoverageCellScore(
        gap_precision=0.5,
        gap_recall=0.25,
        gap_f1=0.125,
        cell_accuracy=0.75,
        n_cells=8,
    )
    d = score.as_dict()
    assert d == {
        "gap_precision": 0.5,
        "gap_recall": 0.25,
        "gap_f1": 0.125,
        "cell_accuracy": 0.75,
        "n_cells": 8,
    }
    assert set(d) == {"gap_precision", "gap_recall", "gap_f1", "cell_accuracy", "n_cells"}
