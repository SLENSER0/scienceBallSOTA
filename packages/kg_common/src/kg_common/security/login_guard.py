"""Login brute-force lockout tracker (§19.2 auth).

Repeated failed logins for the same identity must be throttled and eventually
locked out («блокировка после серии неудачных попыток входа»). This module is
deliberately clock-free: every method takes an explicit ``now`` (a monotonic or
unix timestamp in seconds) so behaviour is fully deterministic and unit-testable
— no wall-clock reads. :class:`LockoutPolicy` is the frozen configuration
(max failures, lockout duration, sliding window); :class:`LoginAttemptTracker`
holds per-key failure timestamps and lock deadlines in memory.

Semantics: a failure "counts" while ``now - failure_ts < window_sec`` (older
failures are pruned). Reaching ``max_failed`` failures inside that window locks
the key until ``failure_ts + lockout_sec``. A successful login clears all state
for the key. Pure-python, no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LockoutPolicy:
    """Brute-force lockout configuration («политика блокировки входа»).

    :param max_failed: failures within the window that trigger a lockout.
    :param lockout_sec: how long the key stays locked once tripped, in seconds.
    :param window_sec: sliding window over which failures accumulate, in seconds.
    """

    max_failed: int = 5
    lockout_sec: float = 900.0
    window_sec: float = 900.0

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the policy («сериализуемое представление»)."""
        return {
            "max_failed": self.max_failed,
            "lockout_sec": self.lockout_sec,
            "window_sec": self.window_sec,
        }


@dataclass
class LoginAttemptTracker:
    """In-memory failed-login tracker enforcing a :class:`LockoutPolicy` (§19.2).

    All time-dependent methods take an explicit ``now`` so no wall clock is read
    («время передаётся явно, часы не читаем»). State is per key (e.g. a username
    or ``user@ip`` pair): recent failure timestamps and, once tripped, the lock
    deadline.
    """

    policy: LockoutPolicy = field(default_factory=LockoutPolicy)
    _failures: dict[str, list[float]] = field(default_factory=dict, init=False, repr=False)
    _locked_until: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def _prune(self, key: str, now: float) -> list[float]:
        """Drop failures older than ``window_sec`` and return the surviving list."""
        cutoff = now - self.policy.window_sec
        recent = [ts for ts in self._failures.get(key, ()) if ts > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def record_failure(self, key: str, now: float) -> None:
        """Record a failed attempt for *key* at *now*; lock the key if tripped."""
        recent = self._prune(key, now)
        recent.append(now)
        self._failures[key] = recent
        if len(recent) >= self.policy.max_failed:
            self._locked_until[key] = now + self.policy.lockout_sec

    def record_success(self, key: str) -> None:
        """Clear all failure and lock state for *key* on a successful login."""
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)

    def failure_count(self, key: str, now: float) -> int:
        """Return the number of failures for *key* still inside the window at *now*."""
        return len(self._prune(key, now))

    def is_locked(self, key: str, now: float) -> bool:
        """True if *key* is currently locked out at *now* («ключ заблокирован»)."""
        deadline = self._locked_until.get(key)
        if deadline is None:
            return False
        if now < deadline:
            return True
        # Lockout has elapsed — clear it so state does not accumulate.
        self._locked_until.pop(key, None)
        return False

    def retry_after(self, key: str, now: float) -> float:
        """Seconds until *key* may retry; ``0.0`` when not locked at *now*."""
        deadline = self._locked_until.get(key)
        if deadline is None or now >= deadline:
            return 0.0
        return deadline - now
