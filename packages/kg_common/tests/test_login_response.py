"""Tests for enumeration-safe login outcome (§19.2 auth)."""

from __future__ import annotations

from kg_common.security.login_response import LoginOutcome, evaluate_login


def test_full_success_is_200_and_login_success() -> None:
    """All checks pass, not locked -> 200 with the success audit event."""
    outcome = evaluate_login(user_exists=True, password_ok=True, is_active=True, locked=False)
    assert outcome.status == 200
    assert outcome.audit_event == "login_success"
    assert outcome.record_failure is False


def test_wrong_password_is_401_and_records_failure() -> None:
    """Existing user, bad password -> uniform 401 that records a failure."""
    outcome = evaluate_login(user_exists=True, password_ok=False, is_active=True, locked=False)
    assert outcome.status == 401
    assert outcome.message == "invalid credentials"
    assert outcome.record_failure is True


def test_nonexistent_user_is_401_invalid_credentials() -> None:
    """Unknown identity -> the same 401 message as a wrong password."""
    outcome = evaluate_login(user_exists=False, password_ok=False, is_active=True, locked=False)
    assert outcome.status == 401
    assert outcome.message == "invalid credentials"


def test_inactive_user_is_401_invalid_credentials() -> None:
    """Valid password on an inactive account -> the same uniform 401."""
    outcome = evaluate_login(user_exists=True, password_ok=True, is_active=False, locked=False)
    assert outcome.status == 401
    assert outcome.message == "invalid credentials"


def test_locked_is_429_and_login_locked_no_failure() -> None:
    """Locked account -> 429 lockout event and no extra failure recorded."""
    outcome = evaluate_login(user_exists=True, password_ok=True, is_active=True, locked=True)
    assert outcome.status == 429
    assert outcome.audit_event == "login_locked"
    assert outcome.record_failure is False


def test_failure_message_is_enumeration_safe() -> None:
    """The failure message must not depend on whether the user exists."""
    exists = evaluate_login(user_exists=True, password_ok=False, is_active=True, locked=False)
    missing = evaluate_login(user_exists=False, password_ok=False, is_active=True, locked=False)
    assert exists.message == missing.message
    assert exists.status == missing.status == 401
    assert exists.audit_event == missing.audit_event == "login_failed"


def test_as_dict_contains_all_fields() -> None:
    """``as_dict`` exposes every outcome field for serialization."""
    outcome: LoginOutcome = evaluate_login(
        user_exists=True, password_ok=True, is_active=True, locked=False
    )
    data = outcome.as_dict()
    assert set(data) == {"status", "message", "record_failure", "audit_event"}
    assert data == {
        "status": 200,
        "message": "ok",
        "record_failure": False,
        "audit_event": "login_success",
    }
