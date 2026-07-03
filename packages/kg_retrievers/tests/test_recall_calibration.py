"""Tests for gold-set recall calibration with Jeffreys smoothing (§25.17)."""

from __future__ import annotations

from kg_retrievers.recall_calibration import (
    CalibratedPrior,
    calibrate_recall,
    jeffreys_recall,
)


def test_jeffreys_full_match_below_one() -> None:
    """(1) k==n==3 -> (3+0.5)/(3+1) == 0.875, strictly below 1.0."""
    assert jeffreys_recall(3, 3) == 0.875
    assert jeffreys_recall(3, 3) < 1.0


def test_jeffreys_empty_is_neutral() -> None:
    """(2) 0/0 collapses to the neutral 0.5, not an undefined ratio."""
    assert jeffreys_recall(0, 0) == 0.5


def test_jeffreys_zero_of_four() -> None:
    """(6) (0+0.5)/(4+1) == 0.1."""
    assert jeffreys_recall(0, 4) == 0.1


def _gold() -> list[dict]:
    # 'physical' modality: 3 gold facts, all extracted (k == n == 3).
    # 'chemical' modality: 6 gold facts, 2 extracted (n >= min_n).
    return [
        {"fact_id": "p1", "modality": "physical"},
        {"fact_id": "p2", "modality": "physical"},
        {"fact_id": "p3", "modality": "physical"},
        {"fact_id": "c1", "modality": "chemical"},
        {"fact_id": "c2", "modality": "chemical"},
        {"fact_id": "c3", "modality": "chemical"},
        {"fact_id": "c4", "modality": "chemical"},
        {"fact_id": "c5", "modality": "chemical"},
        {"fact_id": "c6", "modality": "chemical"},
    ]


def _extraction() -> list[dict]:
    # All physical facts matched; only 2 chemical facts matched.
    return [
        {"fact_id": "p1"},
        {"fact_id": "p2"},
        {"fact_id": "p3"},
        {"fact_id": "c1"},
        {"fact_id": "c2"},
        {"fact_id": "unrelated"},
    ]


def test_full_match_raw_one_smoothed_below() -> None:
    """(3) modality with k==n==3 has recall_raw==1.0 but recall==0.875."""
    priors = calibrate_recall(_gold(), _extraction())
    physical = {p.modality: p for p in priors}["physical"]
    assert physical.k == 3
    assert physical.n == 3
    assert physical.recall_raw == 1.0
    assert physical.recall == 0.875
    assert physical.recall < 1.0


def test_low_confidence_flag() -> None:
    """(4) low_confidence True when n<min_n and False otherwise."""
    priors = calibrate_recall(_gold(), _extraction(), min_n=5)
    by_mod = {p.modality: p for p in priors}
    assert by_mod["physical"].n == 3
    assert by_mod["physical"].low_confidence is True  # 3 < 5
    assert by_mod["chemical"].n == 6
    assert by_mod["chemical"].low_confidence is False  # 6 >= 5


def test_every_prior_is_gold_calibrated() -> None:
    """(5) every prior has calibrated==True and method=='gold_calibrated'."""
    priors = calibrate_recall(_gold(), _extraction())
    assert priors
    assert all(p.calibrated is True for p in priors)
    assert all(p.method == "gold_calibrated" for p in priors)


def test_empty_gold_returns_empty() -> None:
    """(7) empty gold -> []."""
    assert calibrate_recall([], _extraction()) == []
    assert calibrate_recall([], []) == []


def test_as_dict_exposes_raw_and_smoothed() -> None:
    """(8) as_dict() exposes both recall_raw and smoothed recall keys."""
    priors = calibrate_recall(_gold(), _extraction())
    d = priors[0].as_dict()
    assert "recall_raw" in d
    assert "recall" in d
    assert d["recall_raw"] != d["recall"]  # smoothing shifts the estimate


def test_results_sorted_by_modality() -> None:
    """Results are deterministically sorted by modality name."""
    priors = calibrate_recall(_gold(), _extraction())
    mods = [p.modality for p in priors]
    assert mods == sorted(mods)
    assert mods == ["chemical", "physical"]


def test_chemical_counts_and_recall() -> None:
    """Hand-checked chemical group: k=2, n=6 -> raw=1/3, recall=2.5/7."""
    priors = calibrate_recall(_gold(), _extraction())
    chemical = {p.modality: p for p in priors}["chemical"]
    assert chemical.k == 2
    assert chemical.n == 6
    assert chemical.recall_raw == 2 / 6
    assert chemical.recall == 2.5 / 7


def test_frozen_dataclass_defaults() -> None:
    """CalibratedPrior defaults to calibrated=True, method='gold_calibrated'."""
    p = CalibratedPrior(
        context_key="m",
        modality="m",
        k=1,
        n=2,
        recall_raw=0.5,
        recall=jeffreys_recall(1, 2),
        low_confidence=True,
    )
    assert p.calibrated is True
    assert p.method == "gold_calibrated"
    assert p.recall == 1.5 / 3
