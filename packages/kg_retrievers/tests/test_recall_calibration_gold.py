"""Tests for gold-based recall calibration with Jeffreys smoothing (§25.17)."""

from __future__ import annotations

from kg_retrievers.recall_calibration_gold import (
    CalibratedRecall,
    calibrate_recall,
    jeffreys_recall,
)


def _fact(modality: str, i: int) -> dict:
    """Build a gold fact with content fields and a modality label."""
    return {"modality": modality, "subject": f"s{i}", "predicate": "p", "object": f"o{i}"}


def test_jeffreys_recall_known_values() -> None:
    # (k + 0.5) / (n + 1): hand-checked constants from §25.17.
    assert jeffreys_recall(0, 0) == 0.5  # 0.5 / 1
    assert jeffreys_recall(1, 1) == 0.75  # 1.5 / 2
    assert abs(jeffreys_recall(9, 10) - 0.86363636) < 1e-6  # 9.5 / 11


def test_jeffreys_zero_zero_is_neutral_not_extreme() -> None:
    r = jeffreys_recall(0, 0)
    assert r == 0.5
    assert 0.0 < r < 1.0  # never a falsely-confident 0.0 or 1.0


def test_calibrate_recall_nine_of_ten_found() -> None:
    # Ten gold facts in modality "num"; the extractor recovered nine of them.
    gold = [_fact("num", i) for i in range(10)]
    extracted = [_fact("num", i) for i in range(9)]  # missing i == 9

    results = calibrate_recall(gold, extracted)
    assert len(results) == 1
    res = results[0]
    assert res.modality == "num"
    assert res.n_expected == 10
    assert res.n_found == 9
    assert res.recall_raw == 0.9  # 9 / 10, un-smoothed
    assert abs(res.recall - 0.86363636) < 1e-6  # Jeffreys 9.5 / 11
    assert res.calibrated is True
    assert res.method == "gold_calibrated"


def test_zero_of_zero_modality_yields_neutral_recall() -> None:
    # An empty group (n_expected == 0) must collapse to 0.5, not 0/0 or 1.0.
    res = CalibratedRecall(
        modality="empty",
        n_expected=0,
        n_found=0,
        recall_raw=0.0,
        recall=jeffreys_recall(0, 0),
    )
    assert res.recall == 0.5  # neutral, no extreme confidence
    assert res.recall_raw == 0.0
    assert 0.0 < res.recall < 1.0


def test_results_sorted_by_modality() -> None:
    gold = [
        _fact("zeta", 0),
        _fact("alpha", 1),
        _fact("mu", 2),
        _fact("alpha", 3),
    ]
    results = calibrate_recall(gold, [])
    assert [r.modality for r in results] == ["alpha", "mu", "zeta"]
    # "alpha" has two gold facts, none found -> raw 0.0, Jeffreys 0.5 / 3.
    alpha = results[0]
    assert alpha.n_expected == 2
    assert alpha.n_found == 0
    assert alpha.recall_raw == 0.0
    assert abs(alpha.recall - (0.5 / 3.0)) < 1e-12


def test_as_dict_exposes_raw_and_calibrated() -> None:
    gold = [_fact("num", i) for i in range(4)]
    extracted = [_fact("num", i) for i in range(2)]  # 2 of 4 found
    res = calibrate_recall(gold, extracted)[0]

    d = res.as_dict()
    assert d["recall_raw"] == 0.5  # 2 / 4
    assert d["recall"] == jeffreys_recall(2, 4)  # 2.5 / 5 == 0.5
    assert d["n_expected"] == 4
    assert d["n_found"] == 2
    assert d["method"] == "gold_calibrated"
    assert d["calibrated"] is True


def test_empty_gold_yields_empty_list() -> None:
    assert calibrate_recall([], [_fact("num", 0)]) == []


def test_multiple_modalities_matched_independently() -> None:
    gold = [_fact("a", 0), _fact("a", 1), _fact("b", 2)]
    extracted = [_fact("a", 0), _fact("b", 2)]  # a: 1/2, b: 1/1
    results = calibrate_recall(gold, extracted)

    by_mod = {r.modality: r for r in results}
    assert by_mod["a"].n_found == 1 and by_mod["a"].n_expected == 2
    assert by_mod["a"].recall_raw == 0.5
    assert by_mod["b"].n_found == 1 and by_mod["b"].n_expected == 1
    assert by_mod["b"].recall_raw == 1.0
    assert by_mod["b"].recall == 0.75  # Jeffreys 1.5 / 2, below naive 1.0
