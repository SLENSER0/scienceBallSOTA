"""Token-bucket rate-limiting tests (§19.8 rate limiting, for §14 429).

Every test is deterministic: ``now`` is always passed explicitly as a float of
seconds, so no real clock is ever consulted and each asserted value is
hand-checked against the token-bucket arithmetic.
"""

from __future__ import annotations

import pytest

from kg_common.ratelimit import RateLimiter, TokenBucket


def test_first_n_calls_allowed_then_denied() -> None:
    # capacity=3, no refill: exactly 3 tokens, so 3 allowed then the 4th denied.
    limiter = RateLimiter(TokenBucket(capacity=3, refill_per_sec=0.0))
    results = [limiter.allow("client", now=0.0) for _ in range(4)]
    assert results == [True, True, True, False]


def test_refill_after_elapsed_reallows() -> None:
    # capacity=2, 1 token/sec. Drain at t=0, then 1s later one token is back.
    limiter = RateLimiter(TokenBucket(capacity=2, refill_per_sec=1.0))
    assert limiter.allow("c", now=0.0) is True  # 2 -> 1
    assert limiter.allow("c", now=0.0) is True  # 1 -> 0
    assert limiter.allow("c", now=0.0) is False  # empty
    # elapsed 1s * 1 token/sec = 1 token refilled.
    assert limiter.allow("c", now=1.0) is True  # 1 -> 0
    assert limiter.allow("c", now=1.0) is False


def test_remaining_decrements_per_allowed_call() -> None:
    # capacity=5, no refill: each allowed call drops the balance by exactly 1.
    limiter = RateLimiter(TokenBucket(capacity=5, refill_per_sec=0.0))
    assert limiter.remaining("c", 0.0) == 5.0
    assert limiter.allow("c", now=0.0) is True
    assert limiter.remaining("c", 0.0) == 4.0
    assert limiter.allow("c", now=0.0) is True
    assert limiter.remaining("c", 0.0) == 3.0


def test_refill_is_capped_at_capacity() -> None:
    # capacity=3, fast refill. After a long wait the balance saturates at capacity.
    limiter = RateLimiter(TokenBucket(capacity=3, refill_per_sec=10.0))
    assert limiter.allow("c", now=0.0) is True  # 3 -> 2
    # 100s * 10/sec = 1000 tokens, but capped at capacity=3.
    assert limiter.remaining("c", 100.0) == 3.0


def test_separate_keys_are_independent() -> None:
    # capacity=1: draining "a" leaves "b" with its own full budget.
    limiter = RateLimiter(TokenBucket(capacity=1, refill_per_sec=0.0))
    assert limiter.allow("a", now=0.0) is True  # a: 1 -> 0
    assert limiter.allow("a", now=0.0) is False  # a empty
    assert limiter.allow("b", now=0.0) is True  # b untouched, fresh full bucket


def test_reset_restores_full_bucket() -> None:
    # reset() forgets the state so the next access is a fresh, full bucket.
    limiter = RateLimiter(TokenBucket(capacity=1, refill_per_sec=0.0))
    assert limiter.allow("a", now=0.0) is True
    assert limiter.allow("a", now=0.0) is False
    limiter.reset("a")
    assert limiter.remaining("a", 0.0) == 1.0
    assert limiter.allow("a", now=0.0) is True


def test_zero_elapsed_does_not_refill() -> None:
    # Same ``now`` on repeated calls -> elapsed 0 -> no tokens added, stays denied.
    limiter = RateLimiter(TokenBucket(capacity=2, refill_per_sec=5.0))
    assert limiter.allow("c", now=0.0) is True  # 2 -> 1
    assert limiter.allow("c", now=0.0) is True  # 1 -> 0
    assert limiter.allow("c", now=0.0) is False  # empty, elapsed 0
    assert limiter.remaining("c", 0.0) == 0.0  # no refill at the same instant


def test_fractional_refill_accumulates() -> None:
    # capacity=1, 2 tokens/sec: after 0.25s only 0.5 token -> still denied.
    limiter = RateLimiter(TokenBucket(capacity=1, refill_per_sec=2.0))
    assert limiter.allow("c", now=0.0) is True  # 1 -> 0
    assert limiter.remaining("c", 0.25) == 0.5  # 0 + 0.25 * 2
    assert limiter.allow("c", now=0.25) is False  # 0.5 < 1 token
    # another 0.25s adds 0.5 more -> exactly 1 token, now allowed.
    assert limiter.allow("c", now=0.5) is True  # 0.5 + 0.5 -> 1 -> 0


def test_remaining_of_unseen_key_is_full_capacity() -> None:
    limiter = RateLimiter(TokenBucket(capacity=4, refill_per_sec=1.0))
    assert limiter.remaining("never-seen", 123.0) == 4.0


def test_token_bucket_as_dict_and_validation() -> None:
    bucket = TokenBucket(capacity=3.0, refill_per_sec=1.5)
    assert bucket.as_dict() == {"capacity": 3.0, "refill_per_sec": 1.5}
    with pytest.raises(ValueError, match="capacity"):
        TokenBucket(capacity=0.0, refill_per_sec=1.0)
    with pytest.raises(ValueError, match="refill_per_sec"):
        TokenBucket(capacity=1.0, refill_per_sec=-1.0)
    # frozen: config is immutable after construction.
    with pytest.raises(AttributeError):
        bucket.capacity = 9.0  # type: ignore[misc]
