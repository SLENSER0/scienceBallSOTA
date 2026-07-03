"""Sliding-window rate-limiter tests (§19.4).

Every test is deterministic: ``now`` is passed explicitly as a float of seconds,
so no real clock is consulted and each asserted value is hand-checked against
the sliding-window arithmetic for ``WindowConfig(limit=2, window_s=10)``.
"""

from __future__ import annotations

import pytest

from kg_common.security.sliding_window import (
    Decision,
    SlidingWindowLimiter,
    WindowConfig,
)


def _limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(WindowConfig(limit=2, window_s=10.0))


def test_first_call_allowed_with_one_remaining() -> None:
    # Empty window, limit=2: after recording ts 0 exactly one slot is left.
    limiter = _limiter()
    decision = limiter.check("a", 0.0)
    assert decision.allowed is True
    assert decision.remaining == 1


def test_second_call_allowed_with_zero_remaining() -> None:
    # ts 0 already recorded; ts 1 fills the window -> no budget remains.
    limiter = _limiter()
    assert limiter.check("a", 0.0).allowed is True  # window: {0}
    decision = limiter.check("a", 1.0)  # window: {0, 1}
    assert decision.allowed is True
    assert decision.remaining == 0


def test_third_call_denied_with_retry_after_from_oldest() -> None:
    # Window {0, 1} is full at t=2; oldest ts 0 expires at 0 + 10 = 10, so
    # retry_after = 10 - 2 = 8.0.
    limiter = _limiter()
    limiter.check("a", 0.0)
    limiter.check("a", 1.0)
    decision = limiter.check("a", 2.0)
    assert decision.allowed is False
    assert decision.retry_after == 8.0
    assert decision.remaining == 0


def test_call_after_window_expiry_is_allowed_again() -> None:
    # At t=11 both ts 0 and 1 are at/over the cutoff 11 - 10 = 1, so ts 0
    # (<=1) and ts 1 (<=1) are evicted, leaving an empty window.
    limiter = _limiter()
    limiter.check("a", 0.0)
    limiter.check("a", 1.0)
    assert limiter.check("a", 2.0).allowed is False  # still full at t=2
    decision = limiter.check("a", 11.0)
    assert decision.allowed is True
    assert decision.remaining == 1  # only the fresh ts 11 occupies the window


def test_denied_decision_has_positive_retry_after() -> None:
    limiter = _limiter()
    limiter.check("a", 0.0)
    limiter.check("a", 0.0)
    decision = limiter.check("a", 0.0)  # window full, oldest expires at 10
    assert decision.allowed is False
    assert decision.retry_after > 0.0


def test_independent_keys_do_not_share_budget() -> None:
    # Draining key "a" leaves key "b" with its own full window.
    limiter = _limiter()
    limiter.check("a", 0.0)
    limiter.check("a", 1.0)
    assert limiter.check("a", 2.0).allowed is False  # a is full
    decision = limiter.check("b", 2.0)
    assert decision.allowed is True
    assert decision.remaining == 1


def test_remaining_is_never_negative() -> None:
    # Repeated denials at a full window must keep remaining clamped at 0.
    limiter = _limiter()
    limiter.check("a", 0.0)
    limiter.check("a", 0.0)
    for _ in range(5):
        decision = limiter.check("a", 0.0)
        assert decision.remaining == 0
        assert decision.remaining >= 0


def test_decision_as_dict_keys() -> None:
    decision = Decision(allowed=True, remaining=1, retry_after=0.0)
    assert decision.as_dict() == {
        "allowed": True,
        "remaining": 1,
        "retry_after": 0.0,
    }


def test_window_config_as_dict_and_validation() -> None:
    config = WindowConfig(limit=2, window_s=10.0)
    assert config.as_dict() == {"limit": 2, "window_s": 10.0}
    with pytest.raises(ValueError, match="limit"):
        WindowConfig(limit=0, window_s=10.0)
    with pytest.raises(ValueError, match="window_s"):
        WindowConfig(limit=1, window_s=0.0)
    # frozen: config is immutable after construction.
    with pytest.raises(AttributeError):
        config.limit = 9  # type: ignore[misc]


def test_reset_clears_key_state() -> None:
    limiter = _limiter()
    limiter.check("a", 0.0)
    limiter.check("a", 1.0)
    assert limiter.check("a", 2.0).allowed is False
    limiter.reset("a")
    assert limiter.check("a", 2.0).allowed is True  # fresh empty window
