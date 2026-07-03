"""Tests for cross-domain transfer recommendations (§24.12).

Hand-checkable: weights are composition 0.30, process 0.20, equipment 0.20,
geography 0.15, prior_lab 0.15 (sum 1.0). Pure data logic — no store needed.
"""

from __future__ import annotations

import pytest

from kg_retrievers.cross_domain_transfer import (
    REASON_WEIGHTS,
    TransferRecommendation,
    recommend_transfers,
)


def _query() -> dict:
    return {
        "domain": "catalysis",
        "elements": {"Ni", "Al"},
        "process": "cvd",
        "equipment": "furnace_A",
        "geography": "siberia",
        "known_labs": {"lab-7"},
    }


def test_composition_plus_process_scores_half_in_canonical_order() -> None:
    """(1) composition + process → 0.50, reasons in canonical order."""
    cand = {
        "candidate_id": "c1",
        "domain": "battery",
        "elements": {"Ni", "Co"},  # shares Ni
        "process": "cvd",  # exact
    }
    (rec,) = recommend_transfers(_query(), [cand])
    assert rec.candidate_id == "c1"
    assert rec.score == pytest.approx(0.50)
    assert rec.reasons == ("composition_similarity", "process_condition_match")


def test_same_domain_candidate_excluded() -> None:
    """(2) a candidate from the query's own domain is excluded."""
    cand = {"candidate_id": "same", "domain": "catalysis", "elements": {"Ni"}}
    assert recommend_transfers(_query(), [cand]) == ()


def test_zero_score_dropped_when_min_score_positive() -> None:
    """(3) no reason fires → score 0.0, kept by default but dropped if min>0."""
    cand = {"candidate_id": "c0", "domain": "battery", "elements": {"Xe"}}
    (rec,) = recommend_transfers(_query(), [cand])
    assert rec.score == pytest.approx(0.0)
    assert rec.reasons == ()
    assert recommend_transfers(_query(), [cand], min_score=0.01) == ()


def test_composition_overlap_counts_disjoint_does_not() -> None:
    """(4) {'Ni'} overlap fires composition; disjoint set does not."""
    overlap = {"candidate_id": "ov", "domain": "battery", "elements": {"Ni"}}
    disjoint = {"candidate_id": "dj", "domain": "battery", "elements": {"Fe"}}
    recs = {r.candidate_id: r for r in recommend_transfers(_query(), [overlap, disjoint])}
    assert recs["ov"].reasons == ("composition_similarity",)
    assert recs["ov"].score == pytest.approx(0.30)
    # Disjoint elements fire no composition reason (score 0.0), so a positive
    # min_score drops the disjoint candidate while keeping the overlapping one.
    assert recs["dj"].reasons == ()
    kept = recommend_transfers(_query(), [overlap, disjoint], min_score=0.01)
    assert [r.candidate_id for r in kept] == ["ov"]


def test_prior_lab_experience_fires_when_lab_known() -> None:
    """(5) prior_lab_experience fires when candidate lab_id in known_labs."""
    known = {"candidate_id": "k", "domain": "battery", "lab_id": "lab-7"}
    unknown = {"candidate_id": "u", "domain": "battery", "lab_id": "lab-9"}
    recs = {r.candidate_id: r for r in recommend_transfers(_query(), [known, unknown])}
    assert recs["k"].reasons == ("prior_lab_experience",)
    assert recs["k"].score == pytest.approx(0.15)
    assert recs["u"].reasons == ()


def test_tie_broken_by_candidate_id_ascending() -> None:
    """(6) equal scores sort by candidate_id ascending."""
    b = {"candidate_id": "b", "domain": "battery", "elements": {"Ni"}}
    a = {"candidate_id": "a", "domain": "battery", "elements": {"Ni"}}
    recs = recommend_transfers(_query(), [b, a])
    assert [r.candidate_id for r in recs] == ["a", "b"]
    assert recs[0].score == recs[1].score == pytest.approx(0.30)


def test_as_dict_round_trips_reasons_as_list() -> None:
    """(7) as_dict emits reasons as a list."""
    rec = TransferRecommendation(
        candidate_id="c1",
        score=0.50,
        reasons=("composition_similarity", "process_condition_match"),
    )
    d = rec.as_dict()
    assert d == {
        "candidate_id": "c1",
        "score": 0.50,
        "reasons": ["composition_similarity", "process_condition_match"],
    }
    assert isinstance(d["reasons"], list)


def test_reason_weights_sum_to_one() -> None:
    """(8) the five taxonomy weights sum to 1.0."""
    assert set(REASON_WEIGHTS) == {
        "composition_similarity",
        "process_condition_match",
        "equipment_available",
        "geography_analogy",
        "prior_lab_experience",
    }
    assert sum(REASON_WEIGHTS.values()) == pytest.approx(1.0)
    assert REASON_WEIGHTS["composition_similarity"] == max(REASON_WEIGHTS.values())


def test_sorted_by_score_descending() -> None:
    """Higher-scoring candidates lead the ordering."""
    strong = {
        "candidate_id": "strong",
        "domain": "battery",
        "elements": {"Ni"},
        "process": "cvd",
        "equipment": "furnace_A",
        "geography": "siberia",
        "known_labs": None,
        "lab_id": "lab-7",
    }
    weak = {"candidate_id": "weak", "domain": "ceramics", "elements": {"Ni"}}
    recs = recommend_transfers(_query(), [weak, strong])
    assert [r.candidate_id for r in recs] == ["strong", "weak"]
    assert recs[0].score == pytest.approx(1.0)
    assert recs[1].score == pytest.approx(0.30)
