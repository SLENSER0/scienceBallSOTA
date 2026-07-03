"""Enumeration-safe login outcome normalizer (§19.2 auth).

``login_guard.py`` counts failed attempts but never normalizes *what the caller
returns* into a single, uniform outcome. If the response (status, message, audit
event) differs between "no such user", "wrong password" and "inactive account",
an attacker can enumerate valid identities from the differences. This module
collapses every non-success, non-locked case into one identical 401 response
(«ответ одинаков — перечисление пользователей невозможно») and emits the right
audit event and failure-recording flag for each terminal state.

Semantics:
- locked -> 429 «account locked», audit ``login_locked``, do NOT record failure
  (the lockout already tripped; counting again would extend it unfairly).
- full success (user exists, password ok, active, not locked) -> 200 «ok»,
  audit ``login_success``, do NOT record failure.
- every other combination -> 401 with the *same* message «invalid credentials»,
  audit ``login_failed``, record the failure so the guard can throttle.

Pure-python, clock-free, no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Uniform, non-enumerable failure message («единое сообщение об ошибке входа»).
_INVALID_CREDENTIALS = "invalid credentials"


@dataclass(frozen=True)
class LoginOutcome:
    """Normalized login result («нормализованный итог входа»).

    :param status: HTTP status code to return (200 / 401 / 429).
    :param message: client-facing message; identical for all failures.
    :param record_failure: whether the login guard should count this as a
        failed attempt for brute-force throttling.
    :param audit_event: audit log event name for this terminal state.
    """

    status: int
    message: str
    record_failure: bool
    audit_event: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the outcome («сериализуемое представление»)."""
        return {
            "status": self.status,
            "message": self.message,
            "record_failure": self.record_failure,
            "audit_event": self.audit_event,
        }


def evaluate_login(
    *,
    user_exists: bool,
    password_ok: bool,
    is_active: bool,
    locked: bool,
) -> LoginOutcome:
    """Map raw login checks to a uniform, enumeration-safe :class:`LoginOutcome`.

    Order matters: a locked account short-circuits before any credential check
    so a locked identity is never distinguished by password correctness
    («блокировка проверяется первой»). Only a fully valid, active, unlocked
    login succeeds; everything else returns the identical 401 failure so valid
    and invalid usernames are indistinguishable.

    :param user_exists: whether the supplied identity resolves to a real user.
    :param password_ok: whether the supplied password verified.
    :param is_active: whether the resolved account is active (not disabled).
    :param locked: whether the identity is currently locked out.
    :returns: the normalized outcome for this attempt.
    """
    if locked:
        return LoginOutcome(
            status=429,
            message="account locked",
            record_failure=False,
            audit_event="login_locked",
        )
    if user_exists and password_ok and is_active:
        return LoginOutcome(
            status=200,
            message="ok",
            record_failure=False,
            audit_event="login_success",
        )
    return LoginOutcome(
        status=401,
        message=_INVALID_CREDENTIALS,
        record_failure=True,
        audit_event="login_failed",
    )
