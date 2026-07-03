"""Per-user concurrent login-session cap with oldest-session eviction (§19.2).

Enforces a ceiling on the number of simultaneously-active login sessions per
user («лимит одновременных сессий на пользователя»), i.e. device/session-
fixation limiting. This is distinct from:

* ``concurrency_quota.py`` — in-flight request slots (admission control), and
* ``token_revocation.py`` — a ``jti`` blacklist for revoked tokens.

Here we track long-lived login sessions. When opening a new session would push
a user over ``max_sessions``, the oldest sessions (lowest ``created_at``) are
evicted to make room («вытесняем самые старые сессии»).

Clock-free: callers pass ``now`` explicitly, so the registry is deterministic
and hand-checkable in tests. Not thread-safe by itself — wrap in a lock if
shared across threads.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionCapConfig:
    """Immutable per-user session ceiling (§19.2).

    :param max_sessions: макс. одновременно активных сессий на пользователя.
    """

    max_sessions: int

    def __post_init__(self) -> None:
        if self.max_sessions < 1:
            raise ValueError("max_sessions must be >= 1")

    def as_dict(self) -> dict[str, int]:
        """Serialize the config to a plain dict (для конфигов/телеметрии)."""
        return {"max_sessions": self.max_sessions}


@dataclass(frozen=True)
class SessionRecord:
    """One active login session («запись об активной сессии»).

    :param session_id: непрозрачный идентификатор сессии.
    :param user_id: владелец сессии.
    :param created_at: момент создания (для сортировки/вытеснения).
    """

    session_id: str
    user_id: str
    created_at: float

    def as_dict(self) -> dict[str, object]:
        """Serialize the record to a plain dict (для телеметрии/аудита)."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class OpenResult:
    """Outcome of an ``open_session`` call (§19.2).

    :param session_id: идентификатор открытой (или переоткрытой) сессии.
    :param evicted: id вытесненных сессий, старейшие первыми.
    :param active_count: число активных сессий пользователя после операции.
    """

    session_id: str
    evicted: tuple[str, ...]
    active_count: int

    def as_dict(self) -> dict[str, object]:
        """Serialize the result to a plain dict (для телеметрии/аудита)."""
        return {
            "session_id": self.session_id,
            "evicted": list(self.evicted),
            "active_count": self.active_count,
        }


class SessionRegistry:
    """Mutable per-user session accountant for a :class:`SessionCapConfig`.

    Tracks active sessions keyed by ``session_id`` and enforces the per-user
    ceiling by evicting the oldest sessions when a new one would overflow it.
    Clock-free: all timestamps are supplied by the caller.
    """

    def __init__(self, config: SessionCapConfig) -> None:
        self._config = config
        self._sessions: dict[str, SessionRecord] = {}

    @property
    def config(self) -> SessionCapConfig:
        """The immutable config backing this registry."""
        return self._config

    def open_session(self, user_id: str, session_id: str, now: float) -> OpenResult:
        """Open (or refresh) ``session_id`` for ``user_id`` at time ``now``.

        Re-opening an already-active ``session_id`` does not double-count
        («повторное открытие той же сессии не удваивает счётчик»); the existing
        record is kept and no eviction happens. When opening a brand-new
        session would exceed ``max_sessions``, the oldest sessions of that user
        are evicted (lowest ``created_at`` first) to make room.
        """
        existing = self._sessions.get(session_id)
        if existing is not None:
            active = self.active_sessions(user_id)
            return OpenResult(session_id=session_id, evicted=(), active_count=len(active))

        evicted: list[str] = []
        # Oldest-first so surplus sessions are dropped from the front.
        owned = sorted(
            (r for r in self._sessions.values() if r.user_id == user_id),
            key=lambda r: (r.created_at, r.session_id),
        )
        # After adding one, the count must be <= max_sessions.
        surplus = len(owned) + 1 - self._config.max_sessions
        for i in range(max(surplus, 0)):
            victim = owned[i]
            del self._sessions[victim.session_id]
            evicted.append(victim.session_id)

        self._sessions[session_id] = SessionRecord(
            session_id=session_id, user_id=user_id, created_at=now
        )
        active_count = len(self.active_sessions(user_id))
        return OpenResult(session_id=session_id, evicted=tuple(evicted), active_count=active_count)

    def close_session(self, session_id: str) -> bool:
        """Close ``session_id``; return whether a session was actually removed.

        Closing an unknown session is a no-op returning ``False``
        («закрытие несуществующей сессии ничего не меняет»).
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def active_sessions(self, user_id: str) -> tuple[SessionRecord, ...]:
        """Active sessions for ``user_id``, sorted by ``created_at`` ascending."""
        owned = [r for r in self._sessions.values() if r.user_id == user_id]
        owned.sort(key=lambda r: (r.created_at, r.session_id))
        return tuple(owned)
