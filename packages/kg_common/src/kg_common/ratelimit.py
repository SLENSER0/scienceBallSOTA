"""Token-bucket rate limiting — ограничение частоты запросов (§19.8, for §14 429).

When an upstream (LLM provider, graph store, external API) or our own request
handler must cap how often a *client* may act, we use the classic **token
bucket** (§19.8). Each client id owns a bucket of at most ``capacity`` tokens
that refills continuously at ``refill_per_sec`` tokens per second. Every allowed
action costs one token; when the bucket is empty the action is denied and the
caller maps that to an HTTP ``429 Too Many Requests`` (§14).

Design goals:

* **No wall clock in the logic** — детерминизм. Every method takes an explicit
  ``now`` (seconds, a float). Nothing here reads ``time.time``; given the same
  ``now`` sequence the outcome is fully reproducible, which is what makes the
  bucket unit-testable without sleeping.
* **Frozen config, mutable state** — :class:`TokenBucket` is an immutable
  descriptor (``capacity`` / ``refill_per_sec``) with :meth:`TokenBucket.as_dict`;
  the per-client token counts live in :class:`RateLimiter`, keyed by client id.
* **Lazy refill** — мы не крутим таймер. A bucket is refilled on access from the
  elapsed wall time since it was last touched, capped at ``capacity``.

Public API:

* :class:`TokenBucket`  — frozen ``(capacity, refill_per_sec)`` config.
* :class:`RateLimiter`  — per-key buckets; :meth:`~RateLimiter.allow`,
  :meth:`~RateLimiter.remaining`, :meth:`~RateLimiter.reset`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "RateLimiter",
    "TokenBucket",
]


@dataclass(frozen=True, slots=True)
class TokenBucket:
    """Immutable bucket descriptor — конфигурация ведра токенов (§19.8).

    ``capacity`` is the maximum (and initial) number of tokens a client may hold;
    ``refill_per_sec`` is how fast tokens are replenished. Validated on
    construction: ``capacity > 0`` and ``refill_per_sec >= 0`` (a zero refill is a
    legal fixed budget that never replenishes).
    """

    capacity: float
    refill_per_sec: float

    def __post_init__(self) -> None:
        if self.capacity <= 0.0:
            raise ValueError("capacity must be > 0")
        if self.refill_per_sec < 0.0:
            raise ValueError("refill_per_sec must be >= 0")

    def as_dict(self) -> dict[str, float]:
        """Structured, JSON-friendly view — таблица параметров ведра (§19.8)."""
        return {
            "capacity": self.capacity,
            "refill_per_sec": self.refill_per_sec,
        }


@dataclass(slots=True)
class _BucketState:
    """Mutable per-client token count — изменяемое состояние ведра (§19.8).

    ``tokens`` is the current balance; ``updated_at`` is the ``now`` at which it
    was last refreshed, so the next access knows how much time has elapsed.
    """

    tokens: float
    updated_at: float


class RateLimiter:
    """Per-client token-bucket limiter — ограничитель по ключу клиента (§19.8).

    One shared :class:`TokenBucket` config governs every client; each distinct
    ``key`` (client id) gets its own :class:`_BucketState`, created full the first
    time it is seen. All methods take an explicit ``now`` (seconds) so behaviour
    is deterministic and free of any real clock.
    """

    def __init__(self, config: TokenBucket) -> None:
        self.config = config
        self._states: dict[str, _BucketState] = {}

    def _state(self, key: str, now: float) -> _BucketState:
        """Return ``key``'s state, creating a full bucket on first sight (§19.8)."""
        state = self._states.get(key)
        if state is None:
            state = _BucketState(tokens=self.config.capacity, updated_at=now)
            self._states[key] = state
        return state

    def _refill(self, state: _BucketState, now: float) -> None:
        """Replenish ``state`` up to ``now`` — дозаправка токенами (§19.8).

        Only time that has moved *forward* adds tokens: ``elapsed = now -
        updated_at`` seconds contribute ``elapsed * refill_per_sec`` tokens, capped
        at ``capacity``. A non-advancing ``now`` (equal or earlier) is a no-op, so
        repeated calls at the same instant neither refill nor rewind the clock.
        """
        if now > state.updated_at:
            elapsed = now - state.updated_at
            refilled = state.tokens + elapsed * self.config.refill_per_sec
            state.tokens = min(self.config.capacity, refilled)
            state.updated_at = now

    def allow(self, key: str, *, now: float) -> bool:
        """Try to spend one token for ``key`` at ``now`` — пропустить запрос (§19.8).

        The bucket is refilled to ``now`` first; if at least one whole token is
        available it is consumed and ``True`` is returned, otherwise the balance is
        left untouched and ``False`` is returned (the caller maps that to ``429``).
        """
        state = self._state(key, now)
        self._refill(state, now)
        if state.tokens >= 1.0:
            state.tokens -= 1.0
            return True
        return False

    def remaining(self, key: str, now: float) -> float:
        """Tokens available to ``key`` at ``now`` — остаток токенов (§19.8).

        Refills to ``now`` (like :meth:`allow` but without consuming) and returns
        the current balance. A never-seen ``key`` reports the full ``capacity``.
        """
        state = self._state(key, now)
        self._refill(state, now)
        return state.tokens

    def reset(self, key: str) -> None:
        """Forget ``key``'s bucket — сброс состояния (§19.8).

        The next access re-creates it full at that moment's ``now``, restoring the
        client's whole budget. Resetting an unknown key is a no-op.
        """
        self._states.pop(key, None)
