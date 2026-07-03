"""Tests for dagster_run_status — тесты синхронизации статуса (§9.9)."""

from __future__ import annotations

import pytest

from kg_common.dagster_run_status import (
    StatusTransition,
    is_terminal,
    to_job_status,
    transition,
)


def test_to_job_status_started_is_running() -> None:
    assert to_job_status("STARTED") == "running"


def test_to_job_status_starting_is_running() -> None:
    assert to_job_status("STARTING") == "running"


def test_to_job_status_success_is_succeeded() -> None:
    assert to_job_status("SUCCESS") == "succeeded"


def test_to_job_status_queued_and_failure_and_canceling() -> None:
    assert to_job_status("QUEUED") == "queued"
    assert to_job_status("FAILURE") == "failed"
    assert to_job_status("CANCELING") == "canceled"
    assert to_job_status("CANCELED") == "canceled"


def test_to_job_status_bogus_raises() -> None:
    with pytest.raises(ValueError):
        to_job_status("BOGUS")


def test_is_terminal_failed_true_running_false() -> None:
    assert is_terminal("failed") is True
    assert is_terminal("running") is False


def test_is_terminal_all_terminal_states() -> None:
    assert is_terminal("succeeded") is True
    assert is_terminal("canceled") is True
    assert is_terminal("queued") is False


def test_is_terminal_unknown_raises() -> None:
    with pytest.raises(ValueError):
        is_terminal("bogus")


def test_transition_queued_to_running_allowed() -> None:
    t = transition("queued", "running")
    assert t.allowed is True
    assert t.terminal is False


def test_transition_out_of_terminal_disallowed() -> None:
    t = transition("succeeded", "running")
    assert t.allowed is False
    assert t.terminal is True


def test_transition_running_to_succeeded_allowed() -> None:
    t = transition("running", "succeeded")
    assert t.allowed is True
    assert t.terminal is False


def test_transition_as_dict() -> None:
    t = transition("running", "succeeded")
    d = t.as_dict()
    assert d["to_status"] == "succeeded"
    assert d["from_status"] == "running"
    assert d["allowed"] is True
    assert d["terminal"] is False


def test_status_transition_is_frozen() -> None:
    t = StatusTransition("queued", "running", allowed=True, terminal=False)
    with pytest.raises((AttributeError, TypeError)):
        t.allowed = False  # type: ignore[misc]
