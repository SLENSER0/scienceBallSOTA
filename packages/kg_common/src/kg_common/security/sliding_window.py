"""Sliding-window rate limiter — лимитер со скользящим окном (§19.4).

Complements the token-bucket limiter that §19.4 already allows with a precise
sliding-window counter. :class:`SlidingWindowLimiter` keeps, per key, only the
timestamps strictly newer than ``now - window_s`` and admits a request only
while fewer than ``limit`` timestamps remain. Each admitted request records its
own timestamp. :class:`Decision` reports the outcome, the remaining budget and
the ``retry_after`` delay until the oldest in-window timestamp expires.
Реализует точный лимитер со скользящим окном как дополнение к токен-бакету.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class WindowConfig:
    """Immutable sliding-window settings — настройки скользящего окна (§19.4).

    Attributes:
        limit: Max requests allowed within the window — макс. запросов в окне.
        window_s: Window length in seconds — длина окна в секундах.
    """

    limit: int
    window_s: float

    def __post_init__(self) -> None:
        """Validate the window bounds — проверить границы окна (§19.4)."""
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.window_s <= 0:
            raise ValueError("window_s must be > 0")

    def as_dict(self) -> dict[str, object]:
        """Return the config as a plain dict — вернуть конфиг как словарь (§19.4)."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of a sliding-window check — итог проверки окна (§19.4).

    Attributes:
        allowed: Whether the request is admitted — допущен ли запрос.
        remaining: Requests still available in the window — оставшийся лимит.
        retry_after: Seconds until the oldest timestamp expires — задержка (сек).
    """

    allowed: bool
    remaining: int
    retry_after: float

    def as_dict(self) -> dict[str, object]:
        """Return the decision as a plain dict — вернуть решение как словарь (§19.4)."""
        return asdict(self)


class SlidingWindowLimiter:
    """Per-key sliding-window rate limiter — лимитер со скользящим окном (§19.4).

    Stateful: keeps a deque of admitted timestamps per key. On each
    :meth:`check`, timestamps at or before ``now - window_s`` are evicted, so
    only strictly-newer timestamps count against the limit.
    Хранит очередь допущенных меток времени для каждого ключа.
    """

    def __init__(self, config: WindowConfig) -> None:
        """Bind the limiter to a config — привязать лимитер к конфигу (§19.4).

        Args:
            config: Sliding-window settings — настройки скользящего окна.
        """
        self._config = config
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    @property
    def config(self) -> WindowConfig:
        """Return the active window config — вернуть активный конфиг окна (§19.4)."""
        return self._config

    def check(self, key: str, now: float) -> Decision:
        """Evaluate one request for ``key`` at ``now`` — проверить запрос (§19.4).

        Evicts timestamps at or before ``now - window_s``, admits the request
        only while fewer than ``limit`` remain, and records ``now`` when
        admitted. On denial ``retry_after`` is the time until the oldest
        in-window timestamp leaves the window.
        При отказе retry_after — время до выхода старейшей метки из окна.

        Args:
            key: Client identifier — идентификатор клиента.
            now: Current time in seconds — текущее время в секундах.

        Returns:
            The admission :class:`Decision` — решение о допуске запроса.
        """
        limit = self._config.limit
        window_s = self._config.window_s
        hits = self._hits[key]

        cutoff = now - window_s
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) < limit:
            hits.append(now)
            remaining = max(0, limit - len(hits))
            return Decision(allowed=True, remaining=remaining, retry_after=0.0)

        # Window full: the oldest timestamp expires at ``hits[0] + window_s``.
        retry_after = max(0.0, (hits[0] + window_s) - now)
        return Decision(allowed=False, remaining=0, retry_after=retry_after)

    def reset(self, key: str) -> None:
        """Forget all timestamps for ``key`` — сбросить состояние ключа (§19.4).

        Args:
            key: Client identifier to clear — очищаемый идентификатор клиента.
        """
        self._hits.pop(key, None)
