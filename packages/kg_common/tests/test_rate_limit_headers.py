"""Tests for rate-limit 429 response headers — тесты заголовков 429 (§19.4)."""

from __future__ import annotations

from kg_common.security.rate_limit_headers import (
    RateLimitState,
    rate_limit_headers,
    retry_after_seconds,
    too_many,
)


def test_limit_header_equals_str_limit() -> None:
    """(1) X-RateLimit-Limit equals str(limit)."""
    state = RateLimitState(limit=100, remaining=42, reset_at=1_700_000_000.0)
    assert rate_limit_headers(state)["X-RateLimit-Limit"] == "100"


def test_negative_remaining_clamped_to_zero() -> None:
    """(2) Negative remaining is clamped to '0'."""
    state = RateLimitState(limit=100, remaining=-5, reset_at=1_700_000_000.0)
    assert rate_limit_headers(state)["X-RateLimit-Remaining"] == "0"


def test_reset_is_str_int_reset_at() -> None:
    """(3) X-RateLimit-Reset is str(int(reset_at)) — truncates the fraction."""
    state = RateLimitState(limit=100, remaining=1, reset_at=1_700_000_123.987)
    assert rate_limit_headers(state)["X-RateLimit-Reset"] == "1700000123"


def test_retry_after_basic() -> None:
    """(4) retry_after_seconds(100, 90) returns 10."""
    assert retry_after_seconds(100.0, 90.0) == 10


def test_retry_after_past_reset_never_negative() -> None:
    """(5) A past reset returns 0, never negative."""
    assert retry_after_seconds(90.0, 100.0) == 0


def test_retry_after_ceils_fraction() -> None:
    """(6) ceil applies: reset 100.2 at now 100 yields 1."""
    assert retry_after_seconds(100.2, 100.0) == 1


def test_too_many_contains_all_keys() -> None:
    """(7) too_many() dict has Retry-After plus all three X-RateLimit-* keys."""
    state = RateLimitState(limit=60, remaining=0, reset_at=150.0)
    headers = too_many(state, now=140.0)
    assert set(headers) == {
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
    }
    assert headers["Retry-After"] == "10"
    assert headers["X-RateLimit-Limit"] == "60"
    assert headers["X-RateLimit-Remaining"] == "0"
    assert headers["X-RateLimit-Reset"] == "150"


def test_state_as_dict_roundtrips() -> None:
    """(8) RateLimitState.as_dict roundtrips back into an equal state."""
    state = RateLimitState(limit=100, remaining=42, reset_at=1_700_000_000.5)
    assert state.as_dict() == {
        "limit": 100,
        "remaining": 42,
        "reset_at": 1_700_000_000.5,
    }
    assert RateLimitState(**state.as_dict()) == state
