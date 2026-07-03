"""Retry / backoff with jitter tests (§9.7 retries / backoff / failure handling).

All tests are deterministic and instant: ``base_delay`` is ``0.0`` unless a
delay value is under test, and ``sleep`` / ``rng`` are always injected — no real
``time.sleep`` and no real randomness ever run here.
"""

from __future__ import annotations

import pytest

from kg_common.retry import (
    RetryError,
    RetryPolicy,
    backoff_schedule,
    retry,
    retry_call,
)


class Boom(Exception):
    """Retryable transient error used by the tests."""


class Other(Exception):
    """A *non*-listed error that must propagate immediately."""


def test_succeeds_first_try_calls_once() -> None:
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        return "ok"

    assert retry_call(fn, exceptions=(Boom,)) == "ok"
    assert len(calls) == 1  # no retries when the first attempt succeeds


def test_succeeds_on_third_try_calls_three_times() -> None:
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise Boom("transient")
        return "recovered"

    assert retry_call(fn, max_attempts=3, exceptions=(Boom,)) == "recovered"
    assert len(calls) == 3  # failed twice, succeeded on the 3rd


def test_exhausts_raises_retry_error_with_last_exception() -> None:
    calls: list[int] = []

    def fn() -> None:
        calls.append(1)
        raise Boom(f"fail-{len(calls)}")

    with pytest.raises(RetryError) as exc_info:
        retry_call(fn, max_attempts=3, exceptions=(Boom,))

    err = exc_info.value
    assert len(calls) == 3  # exactly max_attempts calls
    assert err.attempts == 3
    assert isinstance(err.last_exception, Boom)
    assert str(err.last_exception) == "fail-3"  # the *last* failure is carried
    assert err.__cause__ is err.last_exception  # chained via ``from``


def test_only_listed_exceptions_are_retried() -> None:
    calls: list[int] = []

    def fn() -> None:
        calls.append(1)
        raise Other("not retryable")

    # ``Other`` is not in ``exceptions`` -> it propagates unchanged, no retry.
    with pytest.raises(Other):
        retry_call(fn, max_attempts=5, exceptions=(Boom,))
    assert len(calls) == 1  # failed once and gave up immediately


def test_backoff_schedule_returns_expected_delays() -> None:
    # Default: base_delay == 0 -> all zeros, fully deterministic.
    assert backoff_schedule(3) == (0.0, 0.0, 0.0)
    # 0, base, base*factor, base*factor**2 ...
    assert backoff_schedule(4, base_delay=1.0, factor=2.0) == (0.0, 1.0, 2.0, 4.0)
    assert backoff_schedule(3, base_delay=0.5, factor=3.0) == (0.0, 0.5, 1.5)
    # A single attempt has just the (zero) leading delay.
    assert backoff_schedule(1, base_delay=9.0) == (0.0,)


def test_backoff_schedule_applies_injected_jitter() -> None:
    # rng returns a constant 0.5 -> "full jitter" halves every delay.
    schedule = backoff_schedule(3, base_delay=2.0, factor=2.0, rng=lambda: 0.5)
    assert schedule == (0.0, 1.0, 2.0)  # 0.5*0, 0.5*2, 0.5*4


def test_backoff_schedule_rejects_zero_attempts() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        backoff_schedule(0)


def test_on_retry_invoked_per_retry_with_attempt_number() -> None:
    seen: list[int] = []
    seen_exc: list[BaseException] = []

    def fn() -> None:
        raise Boom("x")

    def on_retry(attempt: int, exc: BaseException) -> None:
        seen.append(attempt)
        seen_exc.append(exc)

    with pytest.raises(RetryError):
        retry_call(fn, max_attempts=3, exceptions=(Boom,), on_retry=on_retry)

    # 3 attempts -> 2 retries; called with the just-failed attempt numbers.
    assert seen == [1, 2]
    assert all(isinstance(e, Boom) for e in seen_exc)


def test_sleep_injected_called_with_the_right_delays() -> None:
    slept: list[float] = []

    def fn() -> None:
        raise Boom("x")

    with pytest.raises(RetryError):
        retry_call(
            fn,
            max_attempts=3,
            base_delay=1.0,
            factor=2.0,
            exceptions=(Boom,),
            sleep=slept.append,
        )

    # Delays used are schedule[1], schedule[2] = base, base*factor.
    assert slept == [1.0, 2.0]


def test_sleep_not_called_when_success_before_exhaustion() -> None:
    slept: list[float] = []
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise Boom("once")
        return "ok"

    assert (
        retry_call(
            fn,
            max_attempts=3,
            base_delay=5.0,
            exceptions=(Boom,),
            sleep=slept.append,
        )
        == "ok"
    )
    assert slept == [5.0]  # exactly one wait, before the successful 2nd attempt


def test_retry_decorator_form_retries_and_preserves_metadata() -> None:
    calls: list[int] = []

    @retry(max_attempts=3, exceptions=(Boom,))
    def flaky(x: int) -> int:
        """Add one after two transient failures."""
        calls.append(1)
        if len(calls) < 3:
            raise Boom("transient")
        return x + 1

    assert flaky(41) == 42
    assert len(calls) == 3
    # functools.wraps keeps identity/metadata.
    assert flaky.__name__ == "flaky"
    assert flaky.__doc__ == "Add one after two transient failures."


def test_retry_decorator_raises_retry_error_on_exhaustion() -> None:
    slept: list[float] = []

    @retry(max_attempts=2, base_delay=3.0, exceptions=(Boom,), sleep=slept.append)
    def always_fails() -> None:
        raise Boom("nope")

    with pytest.raises(RetryError) as exc_info:
        always_fails()
    assert exc_info.value.attempts == 2
    assert slept == [3.0]  # one retry -> one wait of base_delay


def test_retry_policy_schedule_and_as_dict() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, factor=2.0, exceptions=(Boom,))
    assert policy.schedule() == (0.0, 1.0, 2.0)
    assert policy.as_dict() == {
        "max_attempts": 3,
        "base_delay": 1.0,
        "factor": 2.0,
        "exceptions": ["Boom"],
    }


def test_retry_policy_validates_arguments() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="base_delay"):
        RetryPolicy(base_delay=-1.0)
    with pytest.raises(ValueError, match="factor"):
        RetryPolicy(factor=0.5)
    with pytest.raises(ValueError, match="exceptions"):
        RetryPolicy(exceptions=())
