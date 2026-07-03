"""Rate-limit 429 response headers — заголовки ответа 429 при лимитировании (§19.4).

Emits ``X-RateLimit-Limit``/``Remaining``/``Reset`` headers plus a ``Retry-After``
header for HTTP 429 responses. Frozen :class:`RateLimitState` carries the current
limit window; helpers render integer-string headers and compute the retry delay.
Формирует заголовки лимитов запросов и задержку повторной попытки для ответа 429.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class RateLimitState:
    """Immutable rate-limit window snapshot — снимок окна лимита запросов (§19.4).

    Attributes:
        limit: Max requests allowed in the window — макс. запросов в окне.
        remaining: Requests still available — оставшиеся доступные запросы.
        reset_at: Epoch seconds when the window resets — время сброса окна (сек).
    """

    limit: int
    remaining: int
    reset_at: float

    def as_dict(self) -> dict[str, object]:
        """Return the state as a plain dict — вернуть состояние как словарь (§19.4)."""
        return asdict(self)


def rate_limit_headers(state: RateLimitState) -> dict[str, str]:
    """Build ``X-RateLimit-*`` headers from a state — собрать заголовки лимитов (§19.4).

    Remaining is clamped to ``>= 0`` and ``Reset`` is truncated to an integer.
    Все значения выводятся как целочисленные строки.

    Args:
        state: Source rate-limit window snapshot — исходный снимок окна лимита.

    Returns:
        Mapping of header name to integer-string value — заголовки как строки.
    """
    return {
        "X-RateLimit-Limit": str(state.limit),
        "X-RateLimit-Remaining": str(max(0, state.remaining)),
        "X-RateLimit-Reset": str(int(state.reset_at)),
    }


def retry_after_seconds(reset_at: float, now: float) -> int:
    """Seconds until the window resets — секунды до сброса окна (§19.4).

    Uses ``ceil`` so any fractional remainder rounds up, and never returns a
    negative value for a window that has already reset.
    Никогда не возвращает отрицательное значение.

    Args:
        reset_at: Epoch seconds when the window resets — время сброса (сек).
        now: Current epoch seconds — текущее время (сек).

    Returns:
        Non-negative whole seconds to wait — неотрицательные секунды ожидания.
    """
    return max(0, ceil(reset_at - now))


def too_many(state: RateLimitState, now: float) -> dict[str, str]:
    """Build full 429 headers — собрать полный набор заголовков 429 (§19.4).

    Merges the ``X-RateLimit-*`` headers with a ``Retry-After`` header computed
    from ``state.reset_at`` and ``now``.
    Объединяет заголовки лимитов с заголовком Retry-After.

    Args:
        state: Source rate-limit window snapshot — исходный снимок окна лимита.
        now: Current epoch seconds — текущее время (сек).

    Returns:
        Mapping with ``Retry-After`` and all ``X-RateLimit-*`` keys — все заголовки.
    """
    headers = rate_limit_headers(state)
    headers["Retry-After"] = str(retry_after_seconds(state.reset_at, now))
    return headers
