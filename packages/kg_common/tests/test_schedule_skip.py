"""Tests for schedule skip logic — тесты логики пропуска тика (§9.5)."""

from __future__ import annotations

from kg_common.schedule_skip import TickDecision, advance_cursor, decide_tick


def test_first_run_with_materialization_runs() -> None:
    """No cursor + latest present => run, 'new_materializations'."""
    d = decide_tick(last_run_cursor=None, latest_materialization=5)
    assert d.run is True
    assert d.reason == "new_materializations"


def test_cursor_equals_latest_skips_no_new() -> None:
    """latest == cursor => skip, 'no_new_materializations'."""
    d = decide_tick(last_run_cursor=5, latest_materialization=5)
    assert d.run is False
    assert d.reason == "no_new_materializations"


def test_latest_ahead_of_cursor_runs() -> None:
    """latest > cursor => run."""
    d = decide_tick(last_run_cursor=5, latest_materialization=9)
    assert d.run is True
    assert d.reason == "new_materializations"


def test_no_materialization_at_all() -> None:
    """latest None => skip, 'no_materializations'."""
    d = decide_tick(last_run_cursor=None, latest_materialization=None)
    assert d.run is False
    assert d.reason == "no_materializations"


def test_cursor_ahead_of_latest_skips() -> None:
    """cursor (9) > latest (5) => skip, no new work."""
    d = decide_tick(last_run_cursor=9, latest_materialization=5)
    assert d.run is False
    assert d.reason == "no_new_materializations"


def test_no_materializations_even_with_cursor() -> None:
    """latest None wins over an existing cursor."""
    d = decide_tick(last_run_cursor=7, latest_materialization=None)
    assert d.run is False
    assert d.reason == "no_materializations"


def test_zero_latest_is_not_none() -> None:
    """latest == 0 with no cursor still runs (0 is a real id)."""
    d = decide_tick(last_run_cursor=None, latest_materialization=0)
    assert d.run is True
    assert d.reason == "new_materializations"


def test_advance_cursor_takes_max() -> None:
    """max of two ints."""
    assert advance_cursor(3, 7) == 7
    assert advance_cursor(7, 3) == 7


def test_advance_cursor_none_safe() -> None:
    """None-safe on either side, and both None."""
    assert advance_cursor(None, 4) == 4
    assert advance_cursor(4, None) == 4
    assert advance_cursor(None, None) is None


def test_tick_decision_as_dict() -> None:
    """as_dict() exposes run and reason."""
    d = TickDecision(True, "new_materializations")
    assert d.as_dict()["run"] is True
    assert d.as_dict()["reason"] == "new_materializations"


def test_tick_decision_is_frozen() -> None:
    """Instances are immutable — заморожены."""
    d = TickDecision(False, "no_materializations")
    try:
        d.run = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("TickDecision should be frozen")
