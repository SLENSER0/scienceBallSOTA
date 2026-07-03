"""Contradiction-resolution pick accuracy for the §15.4 heuristic (§18.8)."""

from __future__ import annotations

from pytest import approx

from kg_eval.contradiction_resolution_eval import (
    ResolutionScore,
    evaluate_resolutions,
)


def test_all_correct_perfect_accuracy_and_coverage() -> None:
    # Assertion (1): 3 records, every pick matches gold.
    recs = [
        {"predicted_id": "m1", "gold_id": "m1"},
        {"predicted_id": "m2", "gold_id": "m2"},
        {"predicted_id": "m3", "gold_id": "m3"},
    ]
    s = evaluate_resolutions(recs)
    assert s.accuracy == 1.0
    assert s.coverage == 1.0
    assert s.n_scored == 3
    assert s.n_abstained == 0


def test_one_wrong_pick_two_thirds_accuracy() -> None:
    # Assertion (2): one of three picks is wrong -> 2/3.
    recs = [
        {"predicted_id": "m1", "gold_id": "m1"},
        {"predicted_id": "mX", "gold_id": "m2"},  # wrong side
        {"predicted_id": "m3", "gold_id": "m3"},
    ]
    s = evaluate_resolutions(recs)
    assert s.accuracy == approx(2 / 3)
    assert s.n_scored == 3
    assert s.n_abstained == 0
    assert s.coverage == 1.0


def test_none_prediction_is_abstention_excluded_from_accuracy() -> None:
    # Assertion (3): a None predicted_id abstains; the 2 scored picks are both
    # correct so accuracy stays 1.0 over the reduced denominator.
    recs = [
        {"predicted_id": "m1", "gold_id": "m1"},
        {"predicted_id": None, "gold_id": "m2"},  # abstention
        {"predicted_id": "m3", "gold_id": "m3"},
    ]
    s = evaluate_resolutions(recs)
    assert s.n_abstained == 1
    assert s.n_scored == 2
    assert s.accuracy == 1.0  # abstention neither right nor wrong


def test_all_abstentions_zero_accuracy_no_zero_division() -> None:
    # Assertion (4): every record abstains -> accuracy 0.0, coverage 0.0, n_scored 0.
    recs = [
        {"predicted_id": None, "gold_id": "m1"},
        {"predicted_id": "", "gold_id": "m2"},  # empty string also abstains
        {"predicted_id": None, "gold_id": "m3"},
    ]
    s = evaluate_resolutions(recs)
    assert s.accuracy == 0.0
    assert s.coverage == 0.0
    assert s.n_scored == 0
    assert s.n_abstained == 3


def test_coverage_counts_abstentions_in_denominator() -> None:
    # Assertion (5): 4 records, 1 abstention -> 3 scored / 4 total = 0.75.
    recs = [
        {"predicted_id": "m1", "gold_id": "m1"},
        {"predicted_id": "m2", "gold_id": "m2"},
        {"predicted_id": None, "gold_id": "m3"},  # abstention still in denominator
        {"predicted_id": "m4", "gold_id": "m4"},
    ]
    s = evaluate_resolutions(recs)
    assert s.coverage == approx(3 / 4)
    assert s.n_scored == 3
    assert s.n_abstained == 1
    assert s.accuracy == 1.0


def test_empty_input_all_zero_score() -> None:
    # Assertion (6): no records -> all-zero score, no ZeroDivisionError.
    s = evaluate_resolutions([])
    assert s == ResolutionScore(accuracy=0.0, n_scored=0, n_abstained=0, coverage=0.0)


def test_ids_compared_by_str_across_types() -> None:
    # Assertion (7): predicted int 7 matches gold str "7" under str() comparison.
    recs = [
        {"predicted_id": 7, "gold_id": "7"},
        {"predicted_id": "42", "gold_id": 42},
    ]
    s = evaluate_resolutions(recs)
    assert s.n_scored == 2
    assert s.accuracy == 1.0


def test_as_dict_exposes_all_fields() -> None:
    # Assertion (8): as_dict() carries accuracy/n_scored/n_abstained/coverage.
    recs = [
        {"predicted_id": "m1", "gold_id": "m1"},
        {"predicted_id": "mX", "gold_id": "m2"},
        {"predicted_id": None, "gold_id": "m3"},
    ]
    d = evaluate_resolutions(recs).as_dict()
    assert set(d) == {"accuracy", "n_scored", "n_abstained", "coverage"}
    assert d["n_scored"] == 2
    assert d["n_abstained"] == 1
    assert d["accuracy"] == round(1 / 2, 6) == 0.5
    assert d["coverage"] == round(2 / 3, 6)


def test_resolution_score_is_frozen() -> None:
    s = evaluate_resolutions([{"predicted_id": "m1", "gold_id": "m1"}])
    assert isinstance(s, ResolutionScore)
    try:
        s.accuracy = 0.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ResolutionScore must be frozen")
