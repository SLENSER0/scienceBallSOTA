"""Tests for the sliding-window rate limiter (§14.12).

Ручными расчётами проверяем счётную логику: заполнение окна, отказ на
``max+1`` вызове, восстановление после сдвига времени, убывание остатка,
независимость ключей и вычисление ``reset_epoch``.

Hand-checked coverage of the counting logic: filling the window, denial on the
``max+1`` call, recovery after advancing time, decrementing remaining, key
independence and the ``reset_epoch`` computation.
"""

from __future__ import annotations

from api_gateway.sliding_window_limiter import Decision, SlidingWindowLimiter


def test_first_max_requests_all_allowed() -> None:
    """(1) Первые ``max_requests`` вызовов в один момент проходят."""
    limiter = SlidingWindowLimiter(max_requests=3, window_s=60)
    now = 1000.0
    assert [limiter.check("u", now).allowed for _ in range(3)] == [True, True, True]


def test_over_limit_call_denied() -> None:
    """(2) ``max+1``-й вызов в тот же момент отклоняется."""
    limiter = SlidingWindowLimiter(max_requests=3, window_s=60)
    now = 1000.0
    for _ in range(3):
        limiter.check("u", now)
    assert limiter.check("u", now).allowed is False


def test_allowed_again_after_window_advances() -> None:
    """(3) После сдвига ``now`` на ``window_s + 1`` ключ снова доступен."""
    limiter = SlidingWindowLimiter(max_requests=2, window_s=60)
    now = 1000.0
    limiter.check("u", now)
    limiter.check("u", now)
    assert limiter.check("u", now).allowed is False
    assert limiter.check("u", now + 61).allowed is True


def test_remaining_decrements_to_zero() -> None:
    """(4) ``remaining`` убывает от ``max-1`` до ``0`` по разрешённым вызовам."""
    limiter = SlidingWindowLimiter(max_requests=3, window_s=60)
    now = 1000.0
    assert [limiter.check("u", now).remaining for _ in range(3)] == [2, 1, 0]


def test_denied_decision_remaining_zero() -> None:
    """(5) Отказ сообщает ``remaining == 0``."""
    limiter = SlidingWindowLimiter(max_requests=1, window_s=60)
    now = 1000.0
    limiter.check("u", now)
    denied = limiter.check("u", now)
    assert denied.allowed is False
    assert denied.remaining == 0


def test_distinct_keys_independent_budgets() -> None:
    """(6) Разные ключи имеют независимые бюджеты."""
    limiter = SlidingWindowLimiter(max_requests=2, window_s=60)
    now = 1000.0
    limiter.check("a", now)
    limiter.check("a", now)
    assert limiter.check("a", now).allowed is False
    assert limiter.check("b", now).allowed is True
    assert limiter.check("b", now).allowed is True


def test_reset_epoch_is_first_timestamp_plus_window() -> None:
    """(7) ``reset_epoch == int(first_ts) + window_s`` при полном окне."""
    limiter = SlidingWindowLimiter(max_requests=3, window_s=60)
    first = 1000.5
    d1 = limiter.check("u", first)
    limiter.check("u", first + 1)
    d3 = limiter.check("u", first + 2)
    assert d1.reset_epoch == int(first) + 60
    assert d3.reset_epoch == int(first) + 60


def test_as_dict_keys() -> None:
    """(8) ``Decision.as_dict`` даёт ключи allowed/remaining/reset_epoch."""
    d = Decision(allowed=True, remaining=2, reset_epoch=1060)
    assert set(d.as_dict()) == {"allowed", "remaining", "reset_epoch"}
    assert d.as_dict() == {"allowed": True, "remaining": 2, "reset_epoch": 1060}
