"""Retry with exponential backoff + jitter — повтор с экспоненциальной задержкой (§9.7).

Failure handling for the ingest / graph-upsert pipeline (§9.7 «retries / backoff /
failure handling»). External calls (LLM, graph store, object store) fail
transiently; instead of aborting the whole run we retry a fixed number of times,
waiting a *backoff* delay that grows geometrically, optionally перемешанную
джиттером (jitter) so many workers do not retry in lock-step («thundering herd»).

Design goals:

* **Deterministic in tests** — ``base_delay`` defaults to ``0.0`` so the whole
  schedule collapses to zeros and no real waiting happens. Both the clock
  (``sleep=``) and the randomness (``rng=``) are *injectable*; with the defaults
  there is no real ``time.sleep`` and no jitter, so tests run instantly and are
  fully reproducible.
* **Two call forms** — a :func:`retry` decorator and an eager :func:`retry_call`
  helper, sharing one core loop.
* **Explicit exhaustion** — after the last attempt fails a :class:`RetryError`
  is raised carrying the last exception and the attempt count («исчерпание
  попыток»).

Public API:

* :class:`RetryError`      — raised once all attempts are spent.
* :class:`RetryPolicy`     — frozen descriptor (``max_attempts`` / ``base_delay`` /
  ``factor`` / ``exceptions``) with :meth:`RetryPolicy.as_dict` and
  :meth:`RetryPolicy.schedule`.
* :func:`backoff_schedule` — the delay sequence ``(0, base, base*factor, …)``.
* :func:`retry_call`       — run a zero-arg callable with retries.
* :func:`retry`            — decorator wrapping any callable.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = [
    "RetryError",
    "RetryPolicy",
    "backoff_schedule",
    "retry",
    "retry_call",
]

# Type aliases for the injectable seams (§9.7 «детерминизм в тестах»).
SleepFn = Callable[[float], None]
RngFn = Callable[[], float]
OnRetryFn = Callable[[int, BaseException], None]
ExcTuple = tuple[type[BaseException], ...]

# Default backoff parameters (§9.7).
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.0
DEFAULT_FACTOR = 2.0
DEFAULT_EXCEPTIONS: ExcTuple = (Exception,)


def _no_sleep(_delay: float) -> None:
    """No-op clock — не спим (used when ``base_delay == 0``, §9.7)."""
    return None


def _resolve_sleep(sleep: SleepFn | None, base_delay: float) -> SleepFn:
    """Pick the clock: injected → given; else ``time.sleep`` only if we may wait.

    When ``base_delay == 0`` every delay is ``0`` so we default to a no-op and
    never touch the real clock — that is what keeps tests instant (§9.7).
    """
    if sleep is not None:
        return sleep
    if base_delay > 0.0:
        return time.sleep
    return _no_sleep


class RetryError(Exception):
    """Raised after all attempts are exhausted — попытки исчерпаны (§9.7).

    Carries the *last* underlying exception and the total number of attempts
    made so callers can inspect / log the root cause. The original exception is
    also chained via ``__cause__`` (``raise … from``).
    """

    def __init__(self, last_exception: BaseException, attempts: int) -> None:
        self.last_exception: BaseException = last_exception
        self.attempts: int = attempts
        super().__init__(f"retry exhausted after {attempts} attempt(s): {last_exception!r}")


def backoff_schedule(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    factor: float = DEFAULT_FACTOR,
    *,
    rng: RngFn | None = None,
) -> tuple[float, ...]:
    """Return the per-attempt delay sequence — расписание задержек (§9.7).

    The result has exactly ``max_attempts`` entries: index ``i`` is the delay
    *before* attempt ``i + 1``. The first attempt is never delayed, so the
    schedule is::

        (0, base_delay, base_delay*factor, base_delay*factor**2, …)

    With ``base_delay == 0`` (the default) every entry is ``0`` — fully
    deterministic and instant. If ``rng`` is given it is treated as a
    ``random.random``-equivalent returning a float in ``[0, 1)``; each delay
    ``d`` is scaled to ``d * rng()`` («full jitter»). With ``rng=None`` no
    jitter is applied.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    delays: list[float] = []
    for i in range(max_attempts):
        delay = 0.0 if i == 0 else base_delay * (factor ** (i - 1))
        if rng is not None:
            delay = delay * rng()
        delays.append(delay)
    return tuple(delays)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Immutable retry descriptor — политика повторов (§9.7).

    Bundles the knobs so a policy can be declared once and reused. Validated on
    construction: ``max_attempts >= 1``, ``base_delay >= 0``, ``factor >= 1``,
    non-empty ``exceptions``.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_delay: float = DEFAULT_BASE_DELAY
    factor: float = DEFAULT_FACTOR
    exceptions: ExcTuple = field(default_factory=lambda: DEFAULT_EXCEPTIONS)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0.0:
            raise ValueError("base_delay must be >= 0")
        if self.factor < 1.0:
            raise ValueError("factor must be >= 1")
        if not self.exceptions:
            raise ValueError("exceptions must be a non-empty tuple")

    def schedule(self, *, rng: RngFn | None = None) -> tuple[float, ...]:
        """Delay sequence for this policy (see :func:`backoff_schedule`)."""
        return backoff_schedule(self.max_attempts, self.base_delay, self.factor, rng=rng)

    def as_dict(self) -> dict[str, object]:
        """Structured, JSON-friendly view — таблица параметров повтора (§9.7)."""
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "factor": self.factor,
            "exceptions": [exc.__name__ for exc in self.exceptions],
        }


def retry_call[T](
    fn: Callable[[], T],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    factor: float = DEFAULT_FACTOR,
    exceptions: ExcTuple = DEFAULT_EXCEPTIONS,
    on_retry: OnRetryFn | None = None,
    rng: RngFn | None = None,
    sleep: SleepFn | None = None,
) -> T:
    """Call ``fn`` with retries, returning its value — вызов с повтором (§9.7).

    ``fn`` is invoked up to ``max_attempts`` times. Only exceptions that are
    instances of ``exceptions`` are retried; anything else propagates
    immediately («не глотаем чужие ошибки»). Between attempts we wait
    :func:`backoff_schedule` ``[attempt]`` seconds via ``sleep`` (injectable;
    defaults to no real sleep when ``base_delay == 0``). ``on_retry`` — if given —
    is called as ``on_retry(attempt, exc)`` with the 1-based number of the
    attempt that *just failed*, once per retry. When every attempt fails a
    :class:`RetryError` is raised (chained from the last exception).
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    schedule = backoff_schedule(max_attempts, base_delay, factor, rng=rng)
    do_sleep = _resolve_sleep(sleep, base_delay)
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            if on_retry is not None:
                on_retry(attempt, exc)
            do_sleep(schedule[attempt])
    # ``last_exc`` is set: the loop only breaks after an ``except`` bound it.
    assert last_exc is not None  # narrows type; invariant of the loop
    raise RetryError(last_exc, max_attempts) from last_exc


def retry[T](
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    factor: float = DEFAULT_FACTOR,
    exceptions: ExcTuple = DEFAULT_EXCEPTIONS,
    on_retry: OnRetryFn | None = None,
    *,
    rng: RngFn | None = None,
    sleep: SleepFn | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator form of :func:`retry_call` — декоратор повтора (§9.7).

    ``@retry(max_attempts=3, base_delay=0.0, factor=2.0, exceptions=(Exception,),
    on_retry=None)`` wraps a function so each call is retried per the same rules
    as :func:`retry_call`. Function identity/metadata is preserved via
    :func:`functools.wraps`.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            return retry_call(
                lambda: fn(*args, **kwargs),
                max_attempts=max_attempts,
                base_delay=base_delay,
                factor=factor,
                exceptions=exceptions,
                on_retry=on_retry,
                rng=rng,
                sleep=sleep,
            )

        return wrapper

    return decorator
