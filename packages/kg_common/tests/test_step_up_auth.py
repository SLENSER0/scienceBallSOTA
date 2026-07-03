"""Tests for step-up (re-authentication) requirement policy (§19.2)."""

from __future__ import annotations

from kg_common.security.step_up_auth import (
    StepUpDecision,
    StepUpPolicy,
    is_sensitive,
    requires_step_up,
)


def _policy(max_age_s: float = 300.0) -> StepUpPolicy:
    return StepUpPolicy(
        sensitive_actions=frozenset({"admin:users", "curation:schema_change", "apikey:create"}),
        max_age_s=max_age_s,
    )


def test_recent_auth_is_fresh() -> None:
    # Assertion (1): max_age_s=300, last_auth 100s ago -> not required, fresh.
    now = 1_000.0
    d = requires_step_up(_policy(300.0), "admin:users", last_auth_at=now - 100, now=now)
    assert d.required is False
    assert d.reason == "fresh"


def test_old_auth_is_stale() -> None:
    # Assertion (2): last_auth 400s ago (> 300) -> required, stale.
    now = 1_000.0
    d = requires_step_up(_policy(300.0), "admin:users", last_auth_at=now - 400, now=now)
    assert d.required is True
    assert d.reason == "stale"


def test_never_authenticated() -> None:
    # Assertion (3): last_auth_at None -> required, never.
    now = 1_000.0
    d = requires_step_up(_policy(300.0), "admin:users", last_auth_at=None, now=now)
    assert d.required is True
    assert d.reason == "never"


def test_non_sensitive_action() -> None:
    # Assertion (4): non-sensitive action -> not required, not_sensitive.
    now = 1_000.0
    d = requires_step_up(_policy(300.0), "chat:read", last_auth_at=None, now=now)
    assert d.required is False
    assert d.reason == "not_sensitive"


def test_is_sensitive() -> None:
    # Assertion (5): is_sensitive True for admin:users, False for chat:read.
    p = _policy()
    assert is_sensitive(p, "admin:users") is True
    assert is_sensitive(p, "chat:read") is False


def test_boundary_counts_as_fresh() -> None:
    # Assertion (6): age exactly == max_age_s counts as fresh (not required).
    now = 1_000.0
    d = requires_step_up(_policy(300.0), "admin:users", last_auth_at=now - 300, now=now)
    assert d.required is False
    assert d.reason == "fresh"


def test_stale_decision_required_true() -> None:
    # Assertion (7): a stale sensitive action's decision has required True.
    now = 500.0
    d = requires_step_up(_policy(60.0), "curation:schema_change", last_auth_at=now - 61, now=now)
    assert d.reason == "stale"
    assert d.required is True


def test_as_dict_round_trips_action_and_reason() -> None:
    # Assertion (8): as_dict() round-trips action and reason.
    d = StepUpDecision(action="admin:users", required=True, reason="stale")
    dd = d.as_dict()
    assert dd["action"] == "admin:users"
    assert dd["reason"] == "stale"
    assert dd["required"] is True


def test_just_past_boundary_is_stale() -> None:
    # One tick past the boundary flips fresh -> stale.
    now = 1_000.0
    d = requires_step_up(_policy(300.0), "admin:users", last_auth_at=now - 300.001, now=now)
    assert d.required is True
    assert d.reason == "stale"


def test_policy_as_dict() -> None:
    p = StepUpPolicy(sensitive_actions=frozenset({"b:x", "a:y"}), max_age_s=42.0)
    d = p.as_dict()
    assert d["sensitive_actions"] == ["a:y", "b:x"]  # sorted for determinism
    assert d["max_age_s"] == 42.0


def test_zero_max_age_only_now_is_fresh() -> None:
    # max_age_s=0: only an auth at exactly `now` is fresh; anything older stale.
    now = 10.0
    p = StepUpPolicy(sensitive_actions=frozenset({"admin:users"}), max_age_s=0.0)
    assert requires_step_up(p, "admin:users", last_auth_at=now, now=now).reason == "fresh"
    assert requires_step_up(p, "admin:users", last_auth_at=now - 1, now=now).reason == "stale"


def test_negative_max_age_rejected() -> None:
    for bad in (-1.0, -0.5):
        try:
            StepUpPolicy(sensitive_actions=frozenset(), max_age_s=bad)
        except ValueError:
            continue
        raise AssertionError("expected ValueError for negative max_age_s")


def test_frozen_dataclasses() -> None:
    policy = StepUpPolicy(sensitive_actions=frozenset({"a"}), max_age_s=1.0)
    decision = StepUpDecision(action="a", required=False, reason="fresh")
    for obj, field in ((policy, "max_age_s"), (decision, "required")):
        try:
            setattr(obj, field, 99)
        except Exception:  # frozen dataclass raises FrozenInstanceError
            continue
        raise AssertionError(f"{type(obj).__name__} should be frozen")
