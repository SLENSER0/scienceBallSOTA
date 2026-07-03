"""Hand-checkable tests for §12.4 :mod:`kg_retrievers.score_autocut`."""

from __future__ import annotations

import math

import pytest

from kg_retrievers.score_autocut import (
    CutPoint,
    autocut,
    largest_gap_cut,
    relative_threshold_cut,
)


def test_largest_gap_cuts_at_biggest_drop() -> None:
    # gaps: 0.05, 0.45, 0.05 → biggest at boundary 2 → keep 2, drop tail from idx 2.
    cut = largest_gap_cut([0.9, 0.85, 0.4, 0.35])
    assert cut.index == 2
    assert cut.kept == 2
    assert math.isclose(cut.gap, 0.45, abs_tol=1e-9)
    assert cut.reason == "gap"


def test_min_keep_forces_lower_bound() -> None:
    # Big gap is at boundary 2 but min_keep=3 forbids it → keep at least 3.
    cut = largest_gap_cut([0.9, 0.85, 0.4, 0.35], min_keep=3)
    assert cut.kept >= 3
    assert cut.kept == 3
    assert cut.index == 3


def test_relative_threshold_drops_below_ratio() -> None:
    # top=1.0, ratio 0.5 → threshold 0.5; 0.4 < 0.5 is dropped → keep 2.
    cut = relative_threshold_cut([1.0, 0.6, 0.4], ratio=0.5)
    assert cut.kept == 2
    assert cut.index == 2
    assert cut.reason == "threshold"
    assert math.isclose(cut.gap, 0.2, abs_tol=1e-9)


def test_relative_threshold_all_equal_keeps_all() -> None:
    cut = relative_threshold_cut([0.5, 0.5, 0.5], ratio=0.5)
    assert cut.kept == 3
    assert cut.index == 3
    assert cut.gap == 0.0


def test_empty_scores_gap() -> None:
    cut = largest_gap_cut([])
    assert cut == CutPoint(index=0, kept=0, gap=0.0, reason="gap")


def test_empty_scores_threshold() -> None:
    cut = relative_threshold_cut([])
    assert cut.index == 0
    assert cut.kept == 0


def test_single_score_keeps_one() -> None:
    cut = largest_gap_cut([0.7])
    assert cut.kept == 1
    assert cut.index == 1
    assert cut.gap == 0.0
    thr = relative_threshold_cut([0.7])
    assert thr.kept == 1
    assert thr.index == 1


def test_reason_per_method() -> None:
    assert largest_gap_cut([0.9, 0.1]).reason == "gap"
    assert relative_threshold_cut([0.9, 0.1]).reason == "threshold"


def test_autocut_dispatch_and_unknown() -> None:
    gap = autocut([0.9, 0.85, 0.4, 0.35], method="gap")
    assert gap.reason == "gap"
    assert gap.kept == 2
    thr = autocut([1.0, 0.6, 0.4], method="threshold", ratio=0.5)
    assert thr.reason == "threshold"
    assert thr.kept == 2
    # default method is 'gap'.
    assert autocut([1.0, 0.2]).reason == "gap"
    with pytest.raises(ValueError):
        autocut([1.0, 0.5], method="knee")


def test_autocut_forwards_kwargs() -> None:
    cut = autocut([0.9, 0.85, 0.4, 0.35], method="gap", min_keep=3)
    assert cut.kept == 3


def test_as_dict_round_trips_index_and_kept() -> None:
    cut = largest_gap_cut([0.9, 0.85, 0.4, 0.35])
    data = cut.as_dict()
    assert data["index"] == cut.index == 2
    assert data["kept"] == cut.kept == 2
    assert data["reason"] == "gap"
    assert set(data) == {"index", "kept", "gap", "reason"}
