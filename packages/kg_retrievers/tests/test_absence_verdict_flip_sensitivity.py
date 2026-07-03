"""§25.11 — hand-checkable tests for verdict-flip sensitivity analysis."""

from __future__ import annotations

import math
from itertools import pairwise

from kg_retrievers.absence_verdict_flip_sensitivity import (
    GENUINE_GAP,
    POSSIBLE_MISS,
    FlipSensitivity,
    analyze_flip,
    p_missed,
    recall_for_p_missed,
)


def test_p_missed_even_prior_zero_recall() -> None:
    # e=0.5, r=0: 0.5 / (0.5 + 0.5) = 0.5
    assert p_missed(0.5, 0.0) == 0.5


def test_p_missed_high_prior_zero_recall_rounds_to_prior() -> None:
    # e=0.7, r=0: 0.7 / (0.7 + 0.3) = 0.7
    assert round(p_missed(0.7, 0.0), 3) == 0.7


def test_high_prior_zero_recall_verdict_is_possible_miss() -> None:
    fs = analyze_flip(0.7, 0.0)
    assert fs.current_verdict == POSSIBLE_MISS  # p_missed 0.7 >= 0.60


def test_recall_for_p_missed_reachable_rounds() -> None:
    # 1 - 0.6*0.3 / (0.7*0.4) = 1 - 0.18/0.28 = 0.357142...
    r = recall_for_p_missed(0.7, 0.6)
    assert r is not None
    assert round(r, 3) == 0.357


def test_recall_for_p_missed_unreachable_returns_none() -> None:
    # 1 - 0.6*0.5 / (0.5*0.4) = 1 - 1.5 = -0.5  -> outside [0,1] -> None
    assert recall_for_p_missed(0.5, 0.6) is None


def test_analyze_flip_positive_margin_and_robust() -> None:
    fs = analyze_flip(0.9, 0.1)
    # p_missed = 0.81 / 0.91 = 0.8901...  margin ~0.29 > 0, robust True
    assert fs.margin > 0
    assert fs.robust is True
    assert fs.current_verdict == POSSIBLE_MISS


def test_cell_exactly_at_threshold_zero_margin_not_robust() -> None:
    # e=0.75, r=0.5: 0.375 / 0.625 = 0.6 == threshold
    fs = analyze_flip(0.75, 0.5)
    assert math.isclose(fs.current_p_missed, 0.6, abs_tol=1e-9)
    assert math.isclose(fs.margin, 0.0, abs_tol=1e-9)
    assert fs.robust is False


def test_p_missed_monotonic_decreasing_in_recall() -> None:
    vals = [p_missed(0.7, r / 10.0) for r in range(0, 11)]
    for a, b in pairwise(vals):
        assert b < a  # strictly decreases as recall increases


def test_recall_to_flip_none_when_target_outside_unit_interval() -> None:
    # low prior 0.5: threshold 0.6 unreachable -> recall_to_flip None
    fs = analyze_flip(0.5, 0.2)
    assert fs.recall_to_flip is None


def test_recall_to_flip_present_when_reachable() -> None:
    fs = analyze_flip(0.7, 0.0)
    assert fs.recall_to_flip is not None
    assert round(fs.recall_to_flip, 3) == 0.357


def test_low_prior_high_recall_is_genuine_gap() -> None:
    fs = analyze_flip(0.3, 0.9)
    # p_missed = 0.3*0.1 / (0.03 + 0.7) = 0.03/0.73 = 0.041 < 0.60
    assert fs.current_verdict == GENUINE_GAP
    assert fs.margin < 0


def test_frozen_dataclass_as_dict_roundtrip() -> None:
    fs = analyze_flip(0.9, 0.1)
    d = fs.as_dict()
    assert set(d) == {
        "current_verdict",
        "current_p_missed",
        "recall_to_flip",
        "margin",
        "robust",
    }
    assert d["current_verdict"] == fs.current_verdict
    assert isinstance(fs, FlipSensitivity)
