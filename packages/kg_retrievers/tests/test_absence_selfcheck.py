"""Tests for §25.13 absence self-check roll-up (:mod:`absence_selfcheck`)."""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.absence_selfcheck import (
    HIGH_MISS_AT,
    AbsenceSelfCheck,
    summarize_absence,
)


@dataclass(frozen=True)
class _Gap:
    """Minimal AnnotatedGap-shaped object for the object-input path."""

    gap_id: str
    verdict: str
    p_extractor_missed: float


def _spec_gaps() -> list[dict]:
    """The §25.13 worked example, as dicts."""
    return [
        {"gap_id": "g1", "verdict": "genuine_gap", "p_extractor_missed": 0.1},
        {"gap_id": "g2", "verdict": "possible_miss", "p_extractor_missed": 0.7},
        {"gap_id": "g3", "verdict": "possible_miss", "p_extractor_missed": 0.65},
        {"gap_id": "g4", "verdict": "retracted", "p_extractor_missed": 0.0},
        {"gap_id": "g5", "verdict": "abstain", "p_extractor_missed": 0.5},
        {"gap_id": "g6", "verdict": "present"},
    ]


def test_threshold_constant() -> None:
    assert HIGH_MISS_AT == 0.60


def test_spec_counts() -> None:
    res = summarize_absence(_spec_gaps())
    assert res.n_genuine_gap == 1
    assert res.n_possible_miss == 2
    assert res.n_retracted == 1
    assert res.n_abstain == 1
    assert res.n_present == 1
    assert res.total == 6


def test_spec_warnings() -> None:
    res = summarize_absence(_spec_gaps())
    # g2 (possible_miss, 0.70) and g3 (possible_miss, 0.65) both qualify twice
    # over; genuine_gap 0.1, retracted 0.0, abstain 0.5, present all stay silent.
    assert len(res.high_miss_warnings) == 2
    joined = " ".join(res.high_miss_warnings)
    assert "g2" in joined
    assert "g3" in joined
    assert "g1" not in joined


def test_high_p_present_still_warns() -> None:
    # A non-possible_miss verdict still warns when p crosses the threshold.
    res = summarize_absence(
        [{"gap_id": "gap_hi", "verdict": "genuine_gap", "p_extractor_missed": 0.60}]
    )
    assert res.n_genuine_gap == 1
    assert len(res.high_miss_warnings) == 1
    assert "gap_hi" in res.high_miss_warnings[0]


def test_just_below_threshold_no_warn() -> None:
    res = summarize_absence([{"gap_id": "g", "verdict": "genuine_gap", "p_extractor_missed": 0.59}])
    assert res.high_miss_warnings == []


def test_object_input_path() -> None:
    gaps = [
        _Gap("o1", "possible_miss", 0.9),
        _Gap("o2", "genuine_gap", 0.2),
    ]
    res = summarize_absence(gaps)
    assert res.n_possible_miss == 1
    assert res.n_genuine_gap == 1
    assert len(res.high_miss_warnings) == 1
    assert "o1" in res.high_miss_warnings[0]


def test_covered_folds_into_present() -> None:
    res = summarize_absence([{"gap_id": "c", "verdict": "covered"}])
    assert res.n_present == 1
    assert res.total == 1
    assert res.high_miss_warnings == []


def test_empty_input() -> None:
    res = summarize_absence([])
    assert res.n_genuine_gap == 0
    assert res.n_possible_miss == 0
    assert res.n_retracted == 0
    assert res.n_abstain == 0
    assert res.n_present == 0
    assert res.total == 0
    assert res.high_miss_warnings == []


def test_as_dict_keys() -> None:
    res = summarize_absence(_spec_gaps())
    d = res.as_dict()
    for key in (
        "n_genuine_gap",
        "n_possible_miss",
        "n_retracted",
        "n_abstain",
        "n_present",
        "total",
        "high_miss_warnings",
    ):
        assert key in d
    assert d["total"] == 6
    assert len(d["high_miss_warnings"]) == 2
    assert isinstance(res, AbsenceSelfCheck)
