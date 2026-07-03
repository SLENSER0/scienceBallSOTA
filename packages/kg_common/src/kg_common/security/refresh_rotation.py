"""Refresh-token rotation with reuse (theft) detection (§19.2 auth).

Refresh tokens are single-use: every refresh mints a new token and revokes the
one presented, chaining them into a *family* («семейство токенов»). Presenting a
token that was already rotated away — or a token unknown to the store — is the
classic replay signature of a stolen refresh token; when detected, the whole
family is revoked so neither the attacker nor the victim can keep refreshing.

This module is deliberately clock-free: every mutating call takes an explicit
``now`` (a monotonic or unix timestamp in seconds), so behaviour is fully
deterministic and unit-testable — no wall-clock reads. :class:`RefreshToken` and
:class:`RotationResult` are frozen value objects with ``as_dict()``;
:class:`RefreshTokenStore` holds the mutable active/revoked bookkeeping in
memory. Pure-python, no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RefreshToken:
    """A single refresh token in a rotation chain («звено цепочки refresh»).

    :param token_id: opaque unique id of this token.
    :param family_id: id shared by every token descended from one root login.
    :param issued_at: timestamp the token was minted, in seconds.
    :param parent_id: id of the token this one replaced, or ``None`` for a root.
    """

    token_id: str
    family_id: str
    issued_at: float
    parent_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the token («сериализуемое представление»)."""
        return {
            "token_id": self.token_id,
            "family_id": self.family_id,
            "issued_at": self.issued_at,
            "parent_id": self.parent_id,
        }


@dataclass(frozen=True)
class RotationResult:
    """Outcome of a single :meth:`RefreshTokenStore.rotate` («итог ротации»).

    :param new_token: the freshly minted child, or ``None`` when reuse tripped.
    :param revoked_ids: ids revoked by this call (the presented token, or the
        whole family on reuse), in insertion order.
    :param reuse_detected: ``True`` when a rotated/unknown token was replayed.
    """

    new_token: RefreshToken | None
    revoked_ids: tuple[str, ...]
    reuse_detected: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view of the result («сериализуемое представление»)."""
        return {
            "new_token": self.new_token.as_dict() if self.new_token is not None else None,
            "revoked_ids": list(self.revoked_ids),
            "reuse_detected": self.reuse_detected,
        }


@dataclass
class RefreshTokenStore:
    """In-memory rotating refresh-token store with reuse detection (§19.2).

    Tracks every issued token by id along with its family and revocation state.
    All time-dependent methods take an explicit ``now`` so no wall clock is read
    («время передаётся явно, часы не читаем»).
    """

    _tokens: dict[str, RefreshToken] = field(default_factory=dict, init=False, repr=False)
    _active: set[str] = field(default_factory=set, init=False, repr=False)
    _revoked: set[str] = field(default_factory=set, init=False, repr=False)
    _family: dict[str, set[str]] = field(default_factory=dict, init=False, repr=False)

    def issue_root(self, token_id: str, family_id: str, now: float) -> RefreshToken:
        """Mint a new root token for *family_id* and mark it active («корень цепочки»)."""
        token = RefreshToken(token_id=token_id, family_id=family_id, issued_at=now, parent_id=None)
        self._register(token)
        return token

    def _register(self, token: RefreshToken) -> None:
        """Record *token* as active and attach it to its family index."""
        self._tokens[token.token_id] = token
        self._active.add(token.token_id)
        self._family.setdefault(token.family_id, set()).add(token.token_id)

    def _revoke_family(self, family_id: str) -> tuple[str, ...]:
        """Revoke every still-active token of *family_id*; return revoked ids in order."""
        members = self._family.get(family_id, set())
        revoked = [tid for tid in members if tid in self._active]
        for tid in revoked:
            self._active.discard(tid)
            self._revoked.add(tid)
        return tuple(revoked)

    def rotate(self, presented_id: str, new_token_id: str, now: float) -> RotationResult:
        """Rotate *presented_id* into a fresh child, or trip reuse detection.

        An *active* token is revoked and replaced by a new active child
        (``reuse_detected`` False). A token that is already revoked or entirely
        unknown is a replay: the whole family is revoked and no child is minted
        (``reuse_detected`` True).
        """
        if presented_id in self._active:
            presented = self._tokens[presented_id]
            self._active.discard(presented_id)
            self._revoked.add(presented_id)
            child = RefreshToken(
                token_id=new_token_id,
                family_id=presented.family_id,
                issued_at=now,
                parent_id=presented_id,
            )
            self._register(child)
            return RotationResult(
                new_token=child, revoked_ids=(presented_id,), reuse_detected=False
            )
        # Replay of a rotated token, or an id we never issued -> theft signature.
        known = self._tokens.get(presented_id)
        family_id = known.family_id if known is not None else None
        revoked = self._revoke_family(family_id) if family_id is not None else ()
        return RotationResult(new_token=None, revoked_ids=revoked, reuse_detected=True)

    def is_active(self, token_id: str) -> bool:
        """True if *token_id* is currently active («токен действителен»)."""
        return token_id in self._active
