"""Tests for GraphRAG full-vs-incremental index mode decision (§11.4)."""

from __future__ import annotations

from kg_retrievers.graphrag_index_mode import (
    MODE_FULL,
    MODE_INCREMENTAL,
    REASON_INCREMENTAL_OK,
    REASON_LARGE_DELTA,
    REASON_NO_INCREMENTAL_SUPPORT,
    REASON_NO_PRIOR_BUILD,
    IndexModePlan,
    decide_mode,
)


def test_incremental_when_supported_prior_and_small_delta() -> None:
    plan = decide_mode(True, True, 0.1)
    assert plan.mode == MODE_INCREMENTAL
    assert plan.reason == REASON_INCREMENTAL_OK


def test_no_incremental_support_forces_full() -> None:
    plan = decide_mode(False, True, 0.1)
    assert plan.mode == MODE_FULL
    assert plan.reason == REASON_NO_INCREMENTAL_SUPPORT


def test_no_prior_build_forces_full() -> None:
    plan = decide_mode(True, False, 0.1)
    assert plan.mode == MODE_FULL
    assert plan.reason == REASON_NO_PRIOR_BUILD


def test_large_delta_forces_full() -> None:
    plan = decide_mode(True, True, 0.9)
    assert plan.mode == MODE_FULL
    assert plan.reason == REASON_LARGE_DELTA


def test_threshold_is_exclusive() -> None:
    # A delta exactly at the default threshold (0.5) rebuilds fully.
    plan = decide_mode(True, True, 0.5)
    assert plan.mode == MODE_FULL
    assert plan.reason == REASON_LARGE_DELTA


def test_zero_delta_is_incremental() -> None:
    plan = decide_mode(True, True, 0.0)
    assert plan.mode == MODE_INCREMENTAL
    assert plan.reason == REASON_INCREMENTAL_OK


def test_negative_delta_forces_full() -> None:
    # Out-of-range (negative) delta is not a valid incremental window.
    plan = decide_mode(True, True, -0.1)
    assert plan.mode == MODE_FULL
    assert plan.reason == REASON_LARGE_DELTA


def test_support_blocker_takes_priority() -> None:
    # No support AND no prior build -> support blocker reported first.
    plan = decide_mode(False, False, 0.1)
    assert plan.reason == REASON_NO_INCREMENTAL_SUPPORT


def test_custom_threshold_respected() -> None:
    assert decide_mode(True, True, 0.2, full_rebuild_threshold=0.3).mode == MODE_INCREMENTAL
    assert decide_mode(True, True, 0.3, full_rebuild_threshold=0.3).mode == MODE_FULL


def test_as_dict_shape_and_changed_ratio() -> None:
    plan = decide_mode(True, True, 0.1)
    assert plan.as_dict() == {
        "mode": "incremental",
        "reason": REASON_INCREMENTAL_OK,
        "changed_ratio": 0.1,
    }
    assert plan.as_dict()["changed_ratio"] == 0.1


def test_plan_is_frozen() -> None:
    plan = IndexModePlan(MODE_FULL, REASON_LARGE_DELTA, 0.9)
    try:
        plan.mode = MODE_INCREMENTAL  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("IndexModePlan must be immutable")
