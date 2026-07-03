"""Tests for rate-limit response headers (§14.12).

Hermetic and dependency-free. Every assertion is a concrete hand-checked
value: the exact ``X-RateLimit-*`` string headers, the ``remaining`` clamp at
zero, the ``retry_after`` back-off (positive and collapsed-to-zero cases), the
``too_many`` boundary at an exhausted budget and the exact header-name set.
"""

from __future__ import annotations

from api_gateway.ratelimit_headers import (
    RateLimitHeaders,
    build_headers,
    retry_after,
    too_many,
)


def test_as_headers_remaining_string() -> None:
    # remaining=5 renders as the string "5".
    assert build_headers(100, 5, 200).as_headers()["X-RateLimit-Remaining"] == "5"


def test_build_headers_clamps_negative_remaining() -> None:
    # An over-drawn bucket (-3) is clamped to 0.
    assert build_headers(100, -3, 200).remaining == 0


def test_as_headers_limit_string() -> None:
    assert build_headers(100, 5, 200).as_headers()["X-RateLimit-Limit"] == "100"


def test_retry_after_positive() -> None:
    # 200 - 150 = 50 seconds of back-off.
    assert retry_after(200, 150) == 50


def test_retry_after_collapses_to_zero() -> None:
    # now (150) already past reset (100) → no back-off.
    assert retry_after(100, 150) == 0


def test_too_many_true_when_exhausted() -> None:
    assert too_many(100, 0) is True


def test_too_many_false_with_budget() -> None:
    assert too_many(100, 1) is False


def test_as_headers_name_set() -> None:
    assert set(build_headers(1, 1, 1).as_headers()) == {
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    }


def test_as_dict_shape() -> None:
    # Plain field mirror, unclamped fields preserved.
    assert build_headers(100, 5, 200).as_dict() == {
        "limit": 100,
        "remaining": 5,
        "reset_epoch": 200,
    }


def test_frozen_dataclass_immutable() -> None:
    import dataclasses

    headers = RateLimitHeaders(limit=10, remaining=2, reset_epoch=42)
    try:
        headers.remaining = 0  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guards the frozen contract
        raise AssertionError("RateLimitHeaders must be immutable")


def test_headers_values_are_all_strings() -> None:
    headers = build_headers(100, 5, 200).as_headers()
    assert all(isinstance(v, str) for v in headers.values())
