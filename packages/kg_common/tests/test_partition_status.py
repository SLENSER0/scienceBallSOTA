"""Partition materialization status board tests (§9.6)."""

from __future__ import annotations

import pytest

from kg_common.partition_status import (
    DEFAULT_STATE,
    STATES,
    PartitionStatus,
    StatusBoard,
)


def test_set_and_get_round_trips() -> None:
    board = StatusBoard()
    stored = board.set_status("doc-1", "running", "2026-07-03T10:00:00Z")
    assert isinstance(stored, PartitionStatus)
    got = board.get_status("doc-1")
    assert got.key == "doc-1"
    assert got.state == "running"
    assert got.updated_at == "2026-07-03T10:00:00Z"
    # get_status returns exactly what set_status stored.
    assert got == stored
    assert "doc-1" in board
    assert len(board) == 1


def test_unknown_key_defaults_to_pending() -> None:
    board = StatusBoard()
    got = board.get_status("never-seen")
    assert got.key == "never-seen"
    assert got.state == DEFAULT_STATE == "pending"
    # Never updated — empty explicit timestamp, and the key is not tracked.
    assert got.updated_at == ""
    assert "never-seen" not in board
    assert len(board) == 0


def test_summary_by_state_counts() -> None:
    board = StatusBoard()
    board.set_status("a", "materialized", "2026-07-03T01:00:00Z")
    board.set_status("b", "materialized", "2026-07-03T02:00:00Z")
    board.set_status("c", "running", "2026-07-03T03:00:00Z")
    board.set_status("d", "failed", "2026-07-03T04:00:00Z")
    summary = board.summary()
    # by_state always lists all four canonical states, zero-filled.
    assert summary["by_state"] == {
        "pending": 0,
        "running": 1,
        "materialized": 2,
        "failed": 1,
    }
    # Counts sum to the number of tracked keys.
    assert sum(summary["by_state"].values()) == len(board) == 4


def test_summary_pct_materialized() -> None:
    board = StatusBoard()
    board.set_status("a", "materialized", "2026-07-03T01:00:00Z")
    board.set_status("b", "materialized", "2026-07-03T02:00:00Z")
    board.set_status("c", "running", "2026-07-03T03:00:00Z")
    board.set_status("d", "pending", "2026-07-03T04:00:00Z")
    # 2 of 4 materialized -> exactly 50.0 percent.
    assert board.summary()["pct_materialized"] == 50.0
    # 1 of 3 materialized rounds to four decimals.
    board2 = StatusBoard()
    board2.set_status("x", "materialized", "t1")
    board2.set_status("y", "running", "t2")
    board2.set_status("z", "failed", "t3")
    assert board2.summary()["pct_materialized"] == 33.3333


def test_transitions_last_write_wins() -> None:
    board = StatusBoard()
    board.set_status("doc-1", "pending", "2026-07-03T00:00:00Z")
    board.set_status("doc-1", "running", "2026-07-03T00:05:00Z")
    board.set_status("doc-1", "materialized", "2026-07-03T00:10:00Z")
    got = board.get_status("doc-1")
    # Only the last transition survives; the key is not duplicated.
    assert got.state == "materialized"
    assert got.updated_at == "2026-07-03T00:10:00Z"
    assert len(board) == 1
    assert board.summary() == {
        "by_state": {"pending": 0, "running": 0, "materialized": 1, "failed": 0},
        "pct_materialized": 100.0,
    }


def test_empty_board_summary() -> None:
    board = StatusBoard()
    assert len(board) == 0
    # Empty board: all states zero, no division by zero.
    assert board.summary() == {
        "by_state": {"pending": 0, "running": 0, "materialized": 0, "failed": 0},
        "pct_materialized": 0.0,
    }


def test_as_dict_shape() -> None:
    status = PartitionStatus(key="doc-1", state="materialized", updated_at="2026-07-03T10:00:00Z")
    assert status.as_dict() == {
        "key": "doc-1",
        "state": "materialized",
        "updated_at": "2026-07-03T10:00:00Z",
    }


def test_invalid_state_raises() -> None:
    board = StatusBoard()
    with pytest.raises(ValueError):
        board.set_status("doc-1", "done", "2026-07-03T10:00:00Z")
    # Every canonical state is accepted.
    for state in STATES:
        assert board.set_status("k", state, "t").state == state


def test_partition_status_is_frozen() -> None:
    status = PartitionStatus(key="doc-1", state="pending", updated_at="t")
    with pytest.raises(AttributeError):
        status.state = "running"  # type: ignore[misc]
