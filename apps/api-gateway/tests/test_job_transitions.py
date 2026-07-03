"""Tests for the ingest-job lifecycle state machine (§14.10).

Ручная проверка таблицы переходов, терминальности, ошибки перехода и
идемпотентной семантики отмены (409/200). Hand-checkable assertions over
the transition table, terminality, transition errors and the idempotent
cancel semantics.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.job_transitions import (
    ALLOWED,
    STATUSES,
    TERMINAL,
    CancelOutcome,
    InvalidTransition,
    can_transition,
    cancel,
    is_terminal,
    validate_transition,
)


def test_terminal_set_exact() -> None:
    assert frozenset({"succeeded", "failed", "cancelled"}) == TERMINAL


def test_allowed_table_shape() -> None:
    # Каждый статус — ключ; терминальные не имеют исходящих переходов.
    assert set(ALLOWED) == STATUSES
    for term in TERMINAL:
        assert ALLOWED[term] == frozenset()
    assert ALLOWED["queued"] == frozenset({"running", "cancelled"})
    assert ALLOWED["running"] == frozenset({"succeeded", "failed", "cancelled"})


def test_can_transition_spec_cases() -> None:
    assert can_transition("queued", "running") is True
    assert can_transition("running", "succeeded") is True
    assert can_transition("succeeded", "running") is False
    assert can_transition("queued", "cancelled") is True


def test_can_transition_running_to_failed_and_cancelled() -> None:
    assert can_transition("running", "failed") is True
    assert can_transition("running", "cancelled") is True


def test_can_transition_unknown_source() -> None:
    assert can_transition("bogus", "running") is False


def test_is_terminal_spec_cases() -> None:
    assert is_terminal("cancelled") is True
    assert is_terminal("queued") is False
    assert is_terminal("running") is False
    assert is_terminal("succeeded") is True
    assert is_terminal("failed") is True


def test_validate_transition_allows_valid() -> None:
    # Не бросает для допустимого перехода / returns None on a legal edge.
    assert validate_transition("queued", "running") is None


def test_validate_transition_raises_on_terminal() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition("succeeded", "failed")


def test_validate_transition_raises_backwards() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition("succeeded", "running")


def test_cancel_running_changes() -> None:
    out = cancel("running")
    assert out.status == "cancelled"
    assert out.changed is True
    assert out.conflict is False


def test_cancel_queued_changes() -> None:
    out = cancel("queued")
    assert out == CancelOutcome(status="cancelled", changed=True, conflict=False)


def test_cancel_succeeded_conflict() -> None:
    out = cancel("succeeded")
    assert out.changed is False
    assert out.conflict is True
    assert out.status == "succeeded"


def test_cancel_already_cancelled_is_conflict_idempotent() -> None:
    # Повторная отмена завершённой задачи — 409, статус не меняется.
    out = cancel("cancelled")
    assert out.status == "cancelled"
    assert out.changed is False
    assert out.conflict is True


def test_cancel_outcome_as_dict() -> None:
    assert cancel("running").as_dict() == {
        "status": "cancelled",
        "changed": True,
        "conflict": False,
    }
    assert cancel("failed").as_dict() == {
        "status": "failed",
        "changed": False,
        "conflict": True,
    }


def test_cancel_outcome_is_frozen() -> None:
    out = cancel("queued")
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.status = "running"  # type: ignore[misc]
