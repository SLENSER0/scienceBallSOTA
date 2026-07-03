"""Tests for the §5.10 ingestion stage state machine.

Проверки конечного автомата стадий приёма (§5.10).
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from ingestion_service.ingest_stages import (
    STAGES,
    TERMINAL_STAGES,
    StageState,
    advance,
    can_transition,
    progress_for,
)


def test_stages_constant() -> None:
    assert STAGES == ("queued", "parsing", "storing", "chunking", "done")
    assert set(TERMINAL_STAGES) == {"done", "failed", "cancelled"}


def test_forward_one_step_allowed() -> None:
    assert can_transition("queued", "parsing") is True
    assert can_transition("parsing", "storing") is True
    assert can_transition("storing", "chunking") is True
    assert can_transition("chunking", "done") is True


def test_skipping_forward_not_allowed() -> None:
    assert can_transition("parsing", "done") is False
    assert can_transition("queued", "storing") is False
    assert can_transition("queued", "done") is False


def test_backward_not_allowed() -> None:
    assert can_transition("storing", "parsing") is False
    assert can_transition("chunking", "queued") is False


def test_abort_from_non_terminal_allowed() -> None:
    assert can_transition("parsing", "failed") is True
    assert can_transition("parsing", "cancelled") is True
    assert can_transition("queued", "failed") is True
    assert can_transition("chunking", "cancelled") is True


def test_no_transition_out_of_terminal() -> None:
    assert can_transition("done", "parsing") is False
    assert can_transition("done", "chunking") is False
    assert can_transition("failed", "parsing") is False
    assert can_transition("cancelled", "queued") is False
    # Terminal stages cannot even re-abort.
    assert can_transition("done", "failed") is False


def test_unknown_stage_rejected() -> None:
    assert can_transition("bogus", "parsing") is False


def test_progress_endpoints_and_monotonic() -> None:
    assert progress_for("queued") == 0.0
    assert progress_for("done") == 1.0
    values = [progress_for(s) for s in STAGES]
    # Strictly monotonically increasing across the ladder.
    assert all(a < b for a, b in pairwise(values))
    # Hand-checkable exact fractions: 5 stages → steps of 0.25.
    assert values == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_progress_abort_is_zero_and_unknown_raises() -> None:
    assert progress_for("failed") == 0.0
    assert progress_for("cancelled") == 0.0
    with pytest.raises(ValueError):
        progress_for("bogus")


def test_advance_forward_clears_error_and_sets_progress() -> None:
    state = StageState("parsing", progress=0.25, error=None)
    nxt = advance(state, "storing")
    assert nxt.stage == "storing"
    assert nxt.error is None
    assert nxt.progress == 0.5
    # Frozen: original untouched.
    assert state.stage == "parsing"


def test_advance_carries_prior_error_field_none() -> None:
    state = StageState("queued")
    assert state.progress == 0.0
    assert state.error is None
    nxt = advance(state, "parsing")
    assert nxt.stage == "parsing"
    assert nxt.progress == 0.25


def test_advance_to_failed_stores_error() -> None:
    state = StageState("parsing", progress=0.25)
    nxt = advance(state, "failed", error="parser crashed")
    assert nxt.stage == "failed"
    assert nxt.error == "parser crashed"
    # Progress is preserved (not recomputed) on abort.
    assert nxt.progress == 0.25


def test_advance_to_cancelled_stores_error() -> None:
    state = StageState("storing", progress=0.5)
    nxt = advance(state, "cancelled", error="user cancelled")
    assert nxt.stage == "cancelled"
    assert nxt.error == "user cancelled"


def test_advance_illegal_raises() -> None:
    with pytest.raises(ValueError):
        advance(StageState("parsing"), "done")
    with pytest.raises(ValueError):
        advance(StageState("done"), "parsing")


def test_full_happy_path_walk() -> None:
    state = StageState("queued")
    for nxt in ("parsing", "storing", "chunking", "done"):
        state = advance(state, nxt)
    assert state.stage == "done"
    assert state.progress == 1.0
    assert state.error is None


def test_as_dict_roundtrip_shape() -> None:
    state = StageState("failed", progress=0.5, error="boom")
    assert state.as_dict() == {"stage": "failed", "progress": 0.5, "error": "boom"}
