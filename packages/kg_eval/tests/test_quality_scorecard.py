"""Per-slice data-quality scorecards (§23.24)."""

from __future__ import annotations

import pytest

from kg_eval.quality_scorecard import (
    Scorecard,
    SliceScore,
    build_scorecard,
    slice_score,
)

_WEIGHTS = {"evidence_coverage": 3.0, "linkage": 2.0, "freshness": 1.0}


def test_slice_score_all_ones_is_100() -> None:
    m = {"evidence_coverage": 1.0, "linkage": 1.0, "freshness": 1.0}
    assert slice_score(m, weights=_WEIGHTS) == 100.0


def test_slice_score_all_zeros_is_0() -> None:
    m = {"evidence_coverage": 0.0, "linkage": 0.0, "freshness": 0.0}
    assert slice_score(m, weights=_WEIGHTS) == 0.0


def test_slice_score_weighted_mean_hand_checked() -> None:
    # (1.0*3 + 0.5*2 + 0.0*1) / (3+2+1) = 4/6 -> *100 = 66.666...
    m = {"evidence_coverage": 1.0, "linkage": 0.5, "freshness": 0.0}
    assert slice_score(m, weights=_WEIGHTS) == pytest.approx(100.0 * 4.0 / 6.0)


def test_slice_score_missing_weight_is_ignored() -> None:
    # 'bogus' has no weight; only evidence_coverage counts -> 100.
    m = {"evidence_coverage": 1.0, "bogus": 0.0}
    assert slice_score(m, weights=_WEIGHTS) == 100.0


def test_slice_score_zero_total_weight_is_0() -> None:
    assert slice_score({"bogus": 1.0}, weights=_WEIGHTS) == 0.0


def test_ones_slice_ranks_first_with_100() -> None:
    slices = {
        "lab_bad": {"evidence_coverage": 0.0, "linkage": 0.0, "freshness": 0.0},
        "lab_good": {"evidence_coverage": 1.0, "linkage": 1.0, "freshness": 1.0},
    }
    card = build_scorecard(slices, weights=_WEIGHTS)
    assert card.rows[0].slice_id == "lab_good"
    assert card.rows[0].score == 100.0
    assert card.rows[-1].slice_id == "lab_bad"
    assert card.rows[-1].score == 0.0


def test_worst_length_and_contents() -> None:
    slices = {
        "a": {"evidence_coverage": 0.9, "linkage": 0.9, "freshness": 0.9},
        "b": {"evidence_coverage": 0.1, "linkage": 0.1, "freshness": 0.1},
        "c": {"evidence_coverage": 0.5, "linkage": 0.5, "freshness": 0.5},
        "d": {"evidence_coverage": 0.3, "linkage": 0.3, "freshness": 0.3},
    }
    card = build_scorecard(slices, weights=_WEIGHTS, worst_n=2)
    assert len(card.worst) == min(2, len(slices))
    # Lowest scorer must be present and first in worst.
    assert card.worst[0].slice_id == "b"
    assert card.worst[1].slice_id == "d"


def test_worst_n_clamped_to_len() -> None:
    slices = {"only": {"evidence_coverage": 0.4}}
    card = build_scorecard(slices, weights=_WEIGHTS, worst_n=3)
    assert len(card.worst) == 1
    assert card.worst[0].slice_id == "only"


def test_mean_score_is_average_of_rows() -> None:
    slices = {
        "x": {"evidence_coverage": 1.0, "linkage": 1.0, "freshness": 1.0},
        "y": {"evidence_coverage": 0.0, "linkage": 0.0, "freshness": 0.0},
    }
    card = build_scorecard(slices, weights=_WEIGHTS)
    expected = sum(r.score for r in card.rows) / len(card.rows)
    assert card.mean_score == expected == 50.0


def test_rows_sorted_descending() -> None:
    slices = {
        "a": {"evidence_coverage": 0.2},
        "b": {"evidence_coverage": 0.8},
        "c": {"evidence_coverage": 0.5},
    }
    card = build_scorecard(slices, weights=_WEIGHTS)
    scores = [r.score for r in card.rows]
    assert scores == sorted(scores, reverse=True)
    assert [r.slice_id for r in card.rows] == ["b", "c", "a"]


def test_slice_id_tie_break_lexicographic() -> None:
    slices = {
        "zebra": {"evidence_coverage": 0.5},
        "alpha": {"evidence_coverage": 0.5},
        "mango": {"evidence_coverage": 0.5},
    }
    card = build_scorecard(slices, weights=_WEIGHTS)
    # All equal scores -> ascending slice_id order in rows.
    assert [r.slice_id for r in card.rows] == ["alpha", "mango", "zebra"]


def test_empty_slices_raises() -> None:
    with pytest.raises(ValueError):
        build_scorecard({}, weights=_WEIGHTS)


def test_as_dict_worst_is_list_of_dicts() -> None:
    slices = {
        "a": {"evidence_coverage": 0.9},
        "b": {"evidence_coverage": 0.1},
    }
    card = build_scorecard(slices, weights=_WEIGHTS, worst_n=1)
    d = card.as_dict()
    assert isinstance(d["worst"], list)
    assert all(isinstance(w, dict) for w in d["worst"])
    assert d["worst"][0]["slice_id"] == "b"
    assert isinstance(d["rows"], list)
    assert d["mean_score"] == pytest.approx(50.0)


def test_frozen_dataclasses() -> None:
    ss = SliceScore(slice_id="a", score=50.0, metrics={"m": 0.5})
    with pytest.raises(AttributeError):
        ss.score = 1.0  # type: ignore[misc]
    card = Scorecard(rows=(ss,), worst=(ss,), mean_score=50.0)
    with pytest.raises(AttributeError):
        card.mean_score = 0.0  # type: ignore[misc]
