"""Tests for the deterministic crosswalk conflict policy (§20.3)."""

from __future__ import annotations

from kg_er.crosswalk_policy import (
    CrosswalkDecision,
    CrosswalkThresholds,
    classify_action,
    resolve_or_create,
)


def test_thresholds_defaults_and_as_dict() -> None:
    th = CrosswalkThresholds()
    assert th.auto_merge == 0.9
    assert th.review_low == 0.7
    assert th.as_dict() == {"auto_merge": 0.9, "review_low": 0.7}


def test_classify_action_boundaries() -> None:
    assert classify_action(0.95) == "auto_merge"
    assert classify_action(0.9) == "auto_merge"  # inclusive lower bound
    assert classify_action(0.8) == "review"
    assert classify_action(0.7) == "review"  # inclusive lower bound
    assert classify_action(0.5) == "separate"
    assert classify_action(0.0) == "separate"
    assert classify_action(1.0) == "auto_merge"


def test_classify_action_just_below_boundaries() -> None:
    assert classify_action(0.8999) == "review"
    assert classify_action(0.6999) == "separate"


def test_direct_map_hit_auto_merges() -> None:
    direct_map = {("elabftw", "a"): "material:1"}
    d = resolve_or_create(
        system="elabftw",
        external_id="a",
        direct_map=direct_map,
        match_probability=0.3,  # ignored on a direct hit
        candidate_canonical_id="material:999",
        new_id="material:new",
    )
    assert d.action == "auto_merge"
    assert d.match_probability == 1.0
    assert d.canonical_id == "material:1"
    assert d.review_status == "resolved"
    assert isinstance(d, CrosswalkDecision)


def test_review_miss_is_pending_and_keeps_candidate() -> None:
    d = resolve_or_create(
        system="elabftw",
        external_id="b",
        direct_map={("elabftw", "a"): "material:1"},
        match_probability=0.8,
        candidate_canonical_id="material:42",
        new_id="material:new",
    )
    assert d.action == "review"
    assert d.review_status == "pending"
    assert d.canonical_id == "material:42"
    assert d.match_probability == 0.8


def test_separate_miss_mints_new_id() -> None:
    d = resolve_or_create(
        system="elabftw",
        external_id="c",
        direct_map={("elabftw", "a"): "material:1"},
        match_probability=0.5,
        candidate_canonical_id="material:42",
        new_id="material:new",
    )
    assert d.action == "separate"
    assert d.canonical_id == "material:new"
    assert d.review_status == "resolved"


def test_auto_merge_miss_uses_candidate() -> None:
    d = resolve_or_create(
        system="elabftw",
        external_id="d",
        direct_map={},
        match_probability=0.95,
        candidate_canonical_id="material:7",
        new_id="material:new",
    )
    assert d.action == "auto_merge"
    assert d.canonical_id == "material:7"
    assert d.review_status == "resolved"
    assert d.match_probability == 0.95


def test_none_probability_is_separate() -> None:
    d = resolve_or_create(
        system="elabftw",
        external_id="e",
        direct_map={},
        match_probability=None,
        candidate_canonical_id=None,
        new_id="material:new",
    )
    assert d.action == "separate"
    assert d.canonical_id == "material:new"
    assert d.review_status == "resolved"
    assert d.match_probability is None


def test_review_without_candidate_falls_back_to_new_id() -> None:
    d = resolve_or_create(
        system="elabftw",
        external_id="f",
        direct_map={},
        match_probability=0.75,
        candidate_canonical_id=None,
        new_id="material:fresh",
    )
    assert d.action == "review"
    assert d.review_status == "pending"
    assert d.canonical_id == "material:fresh"


def test_custom_thresholds_shift_boundaries() -> None:
    th = CrosswalkThresholds(auto_merge=0.8, review_low=0.6)
    assert classify_action(0.85, th) == "auto_merge"
    assert classify_action(0.65, th) == "review"
    assert classify_action(0.55, th) == "separate"


def test_decision_as_dict_roundtrip() -> None:
    d = resolve_or_create(
        system="elabftw",
        external_id="a",
        direct_map={("elabftw", "a"): "material:1"},
        match_probability=None,
        candidate_canonical_id=None,
        new_id="material:new",
    )
    assert d.as_dict() == {
        "system": "elabftw",
        "external_id": "a",
        "action": "auto_merge",
        "match_probability": 1.0,
        "canonical_id": "material:1",
        "review_status": "resolved",
    }
