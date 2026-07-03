"""Sliding-window rate limiter (§14.12).

Счётная логика скользящего окна на чистом stdlib. Модуль
:mod:`ratelimit_headers` умеет лишь форматировать заголовки, а §14.12 требует
самого лимитера: для каждого ключа (пользователь/IP) хранится список меток
времени, при проверке из него выбрасываются метки старше ``now - window_s``.
:class:`Decision` — неизменяемое решение ``(allowed, remaining, reset_epoch)``
с методом :meth:`Decision.as_dict`, а :class:`SlidingWindowLimiter` держит
in-memory словарь ``key -> list[timestamp]`` и решает по методу
:meth:`SlidingWindowLimiter.check`.

Sliding-window counting logic on the standard library only. The
:mod:`ratelimit_headers` module only formats headers, but §14.12 needs the
limiter itself: per key (user/IP) a list of timestamps is kept, and each check
prunes entries older than ``now - window_s``. :class:`Decision` is a frozen
``(allowed, remaining, reset_epoch)`` verdict with :meth:`Decision.as_dict`,
and :class:`SlidingWindowLimiter` holds an in-memory ``key -> list[timestamp]``
dict, deciding through :meth:`SlidingWindowLimiter.check`.

* :class:`Decision`             — frozen ``{allowed, remaining, reset_epoch}`` verdict.
* :class:`SlidingWindowLimiter` — per-key sliding window over an in-memory dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Decision:
    """Неизменяемое решение лимитера (§14.12).

    Frozen verdict returned by :meth:`SlidingWindowLimiter.check`. ``allowed``
    tells whether the call passed, ``remaining`` is the budget left after this
    call (``0`` when denied) and ``reset_epoch`` is the integer epoch second at
    which the oldest kept timestamp falls out of the window.
    """

    allowed: bool
    remaining: int
    reset_epoch: int

    def as_dict(self) -> dict[str, Any]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "reset_epoch": self.reset_epoch,
        }


class SlidingWindowLimiter:
    """Скользящее окно ``max_requests`` за ``window_s`` секунд (§14.12).

    In-memory sliding-window limiter. State is a plain ``dict`` mapping each
    key to the sorted list of timestamps still inside the current window.
    :meth:`check` prunes stale timestamps, appends ``now`` when the budget
    allows and returns a :class:`Decision`; distinct keys never share a budget.
    """

    def __init__(self, max_requests: int, window_s: int) -> None:
        """``max_requests`` вызовов на окно ``window_s`` / calls per window."""
        self.max_requests = max_requests
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, now: float) -> Decision:
        """Решить, пропустить ли вызов ``key`` в момент ``now`` (§14.12).

        Prune timestamps older than ``now - window_s`` for ``key``, then either
        append ``now`` (allowed) or leave the window untouched (denied). The
        ``reset_epoch`` is ``int(oldest_kept + window_s)`` — the instant the
        earliest surviving timestamp expires; when denied ``remaining`` is ``0``.
        """
        cutoff = now - self.window_s
        hits = [ts for ts in self._hits.get(key, []) if ts > cutoff]

        if len(hits) < self.max_requests:
            hits.append(now)
            allowed = True
            remaining = self.max_requests - len(hits)
        else:
            allowed = False
            remaining = 0

        self._hits[key] = hits
        oldest = hits[0] if hits else now
        reset_epoch = int(oldest + self.window_s)
        return Decision(allowed=allowed, remaining=remaining, reset_epoch=reset_epoch)
