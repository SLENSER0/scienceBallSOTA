"""JWT signing keyset and kid rotation resolver (§19.2 auth).

A :class:`JwtKeyset` holds an immutable set of :class:`KeyRef` entries, each
describing one signing/verification key with its ``kid``, algorithm and validity
window ``[not_before, not_after)`` («окно действия ключа»). Pure selection
helpers resolve which key to *sign* with now (:func:`active_signing_key`), how to
*verify* a token by its ``kid`` (:func:`verification_key`) and which ``kid`` are
currently valid (:func:`valid_kids`). This lets keys be rotated ahead of time —
a new signing key is published with a future ``not_before`` and, once its window
opens, it wins over the older overlapping key («новый ключ побеждает при
перекрытии»). No cryptography here: this module only selects key references.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class KeyRef:
    """One key reference in a keyset («ссылка на ключ»).

    ``not_before`` / ``not_after`` bound the half-open validity window
    ``[not_before, not_after)`` (seconds, epoch or relative). ``is_signing``
    marks keys eligible to *sign* new tokens; every key may still *verify*.
    """

    kid: str
    alg: str
    not_before: float
    not_after: float
    is_signing: bool

    def covers(self, now: float) -> bool:
        """True if *now* falls in ``[not_before, not_after)`` («покрывает момент»)."""
        return self.not_before <= now < self.not_after

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-ready mapping («сериализация в словарь»)."""
        return {
            "kid": self.kid,
            "alg": self.alg,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "is_signing": self.is_signing,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeyRef:
        """Rebuild a :class:`KeyRef` from :meth:`as_dict` output."""
        return cls(
            kid=str(data["kid"]),
            alg=str(data["alg"]),
            not_before=float(data["not_before"]),
            not_after=float(data["not_after"]),
            is_signing=bool(data["is_signing"]),
        )


@dataclass(frozen=True, slots=True)
class JwtKeyset:
    """Immutable ordered set of :class:`KeyRef` («набор ключей JWT»)."""

    keys: tuple[KeyRef, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready mapping («сериализация набора»)."""
        return {"keys": [k.as_dict() for k in self.keys]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JwtKeyset:
        """Rebuild a :class:`JwtKeyset` from :meth:`as_dict` output."""
        return cls(keys=tuple(KeyRef.from_dict(k) for k in data["keys"]))


def active_signing_key(keyset: JwtKeyset, now: float) -> KeyRef:
    """Return the signing key whose window covers *now* (§19.2).

    Only ``is_signing`` keys are considered. On overlapping windows the newest
    key wins — the one with the largest ``not_before`` («новее — побеждает»).
    Ties on ``not_before`` are broken by ``kid`` for determinism. Raises
    :class:`LookupError` if no signing key covers *now*.
    """
    candidates = [k for k in keyset.keys if k.is_signing and k.covers(now)]
    if not candidates:
        raise LookupError(f"no active signing key at now={now!r}")
    return max(candidates, key=lambda k: (k.not_before, k.kid))


def verification_key(keyset: JwtKeyset, kid: str) -> KeyRef | None:
    """Return the key with *kid*, or ``None`` if absent («ключ для проверки»)."""
    for k in keyset.keys:
        if k.kid == kid:
            return k
    return None


def valid_kids(keyset: JwtKeyset, now: float) -> frozenset[str]:
    """Return the ``kid`` of every key whose window covers *now* (§19.2)."""
    return frozenset(k.kid for k in keyset.keys if k.covers(now))
