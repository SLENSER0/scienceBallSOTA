"""Access-token ``jti`` revocation blacklist (§19.2 auth).

Short-lived access tokens can be invalidated before their natural expiry by
blacklisting their unique ``jti`` claim («идентификатор токена»). This module
keeps an in-memory map ``jti -> expires_at``: a revoked token stays on the list
only until its own expiry — after that it can never be presented anyway, so the
entry is dead weight and :meth:`RevocationList.prune` can drop it.

The module is deliberately clock-free: every time-dependent call takes an
explicit ``now`` (a unix/monotonic timestamp in seconds), so behaviour is fully
deterministic and unit-testable — no wall-clock reads («время передаётся явно»).
:class:`RevokedToken` is a frozen value object with ``as_dict()``;
:class:`RevocationList` holds the mutable bookkeeping. Pure-python, no
third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RevokedToken:
    """A single blacklisted access token («отозванный токен доступа»).

    :param jti: opaque unique id of the token (its ``jti`` claim).
    :param expires_at: timestamp the token expires on its own, in seconds; the
        blacklist entry is meaningless once ``now >= expires_at``.
    """

    jti: str
    expires_at: float

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the token («сериализуемое представление»)."""
        return {"jti": self.jti, "expires_at": self.expires_at}


@dataclass
class RevocationList:
    """In-memory access-token ``jti`` blacklist with expiry pruning (§19.2).

    Maps each revoked ``jti`` to the timestamp it would expire on its own. A
    token is considered revoked only while it is both stored *and* still before
    its expiry: once ``now >= expires_at`` it is no longer treated as revoked
    (it is already useless), even if the entry has not been pruned yet
    («время передаётся явно, часы не читаем»).
    """

    _revoked: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def revoke(self, jti: str, expires_at: float) -> None:
        """Blacklist *jti* until *expires_at* («занести токен в чёрный список»).

        Revoking the same ``jti`` again just overwrites its expiry — the list
        never holds duplicate entries for one token.
        """
        self._revoked[jti] = expires_at

    def is_revoked(self, jti: str, now: float) -> bool:
        """True if *jti* is blacklisted and not yet past its expiry at *now*.

        Returns ``False`` for an unknown ``jti`` and for a stored one whose
        expiry has already passed (``now >= expires_at``).
        """
        expires_at = self._revoked.get(jti)
        if expires_at is None:
            return False
        return now < expires_at

    def prune(self, now: float) -> int:
        """Drop entries whose expiry has passed; return how many were removed.

        An entry is expired when ``now >= expires_at`` («срок действия истёк»).
        """
        expired = [jti for jti, exp in self._revoked.items() if now >= exp]
        for jti in expired:
            del self._revoked[jti]
        return len(expired)

    def active(self, now: float) -> tuple[RevokedToken, ...]:
        """Return still-effective revocations at *now* («действующие отзывы»)."""
        return tuple(
            RevokedToken(jti=jti, expires_at=exp) for jti, exp in self._revoked.items() if now < exp
        )

    def __len__(self) -> int:
        """Number of stored entries, expired or not («размер чёрного списка»)."""
        return len(self._revoked)
