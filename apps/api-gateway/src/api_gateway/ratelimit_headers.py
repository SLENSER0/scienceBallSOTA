"""Rate-limit response headers (§14.12).

Сборка стандартных заголовков ``X-RateLimit-*`` и вычисление ``Retry-After``
на чистом stdlib. Модуль :mod:`ratelimit` содержит только token-bucket, а §14.12
требует отдавать клиенту лимит, остаток и момент сброса в HTTP-заголовках;
:class:`RateLimitHeaders` — неизменяемая тройка со строковой сериализацией,
:func:`build_headers` собирает её (остаток обрезается до ``>=0``),
:func:`retry_after` даёт паузу в секундах, а :func:`too_many` сигналит отказ.

Rate-limit response headers on the standard library only. The :mod:`ratelimit`
module holds just the token bucket, but §14.12 requires surfacing the limit,
remaining budget and reset instant to the client as HTTP headers.
:class:`RateLimitHeaders` is a frozen triple with string serialisation,
:func:`build_headers` assembles it (remaining clamped to ``>=0``),
:func:`retry_after` yields the back-off seconds and :func:`too_many` flags a 429.

* :class:`RateLimitHeaders` — frozen ``{limit, remaining, reset_epoch}`` triple.
* :func:`build_headers`     — construct the triple, clamping ``remaining`` to ``>=0``.
* :func:`retry_after`       — ``max(0, reset_epoch - now)`` back-off seconds.
* :func:`too_many`          — ``True`` when the budget is exhausted (429).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RateLimitHeaders:
    """Неизменяемая тройка лимита для заголовков ``X-RateLimit-*`` (§14.12).

    Frozen carrier for the ``X-RateLimit-Limit/Remaining/Reset`` values. All
    three fields are integers; :meth:`as_headers` renders them as the exact
    string header dict expected on an HTTP response.
    """

    limit: int
    remaining: int
    reset_epoch: int

    def as_dict(self) -> dict[str, Any]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_epoch": self.reset_epoch,
        }

    def as_headers(self) -> dict[str, str]:
        """Три строковых заголовка ``X-RateLimit-*`` / the three string headers."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }


def build_headers(limit: int, remaining: int, reset_epoch: int) -> RateLimitHeaders:
    """Собрать :class:`RateLimitHeaders`, обрезая ``remaining`` до ``>=0`` (§14.12).

    A negative ``remaining`` (an over-drawn bucket) is clamped to ``0`` so the
    emitted header never goes below zero; ``limit`` and ``reset_epoch`` pass
    through unchanged.
    """
    return RateLimitHeaders(
        limit=limit,
        remaining=max(0, remaining),
        reset_epoch=reset_epoch,
    )


def retry_after(reset_epoch: int, now: int) -> int:
    """Пауза ``Retry-After`` в секундах: ``max(0, reset_epoch - now)`` (§14.12).

    Never negative: once ``now`` reaches or passes ``reset_epoch`` the back-off
    collapses to ``0``.
    """
    return max(0, reset_epoch - now)


def too_many(limit: int, remaining: int) -> bool:
    """``True`` если бюджет исчерпан (429) / budget exhausted → 429 (§14.12).

    A positive ``limit`` with no ``remaining`` budget means the caller must be
    rejected. ``remaining`` is compared as-is, so any value ``<=0`` trips it.
    """
    return limit > 0 and remaining <= 0
