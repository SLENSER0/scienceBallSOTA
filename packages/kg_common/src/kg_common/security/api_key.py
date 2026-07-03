"""API-key generation, hashing & verification (§19.2 auth).

Issue and verify opaque API keys («ключи API») without ever persisting the
plaintext. A key is minted from caller-supplied raw entropy: the wire form is
``prefix + base32(raw)`` and the server stores only a SHA-256 hex digest of that
plaintext inside a frozen :class:`ApiKeyRecord`. Verification recomputes the
digest over the presented plaintext and compares it in constant time
(«постоянное время») via :func:`hmac.compare_digest`, so the record is safe to
log, cache, or serialize — :meth:`ApiKeyRecord.as_dict` never carries the
plaintext. Generation is deterministic for a fixed ``(raw, prefix)`` pair, which
keeps the hand-checkable tests reproducible. Expiry («истечение срока») is an
optional wall-clock bound evaluated by :func:`is_expired`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ApiKeyRecord:
    """Immutable, plaintext-free record of an issued API key («запись ключа»).

    :param key_id: stable opaque identifier for the key.
    :param prefix: human-visible key prefix (e.g. ``"sk_"``).
    :param key_hash: lowercase hex SHA-256 of the plaintext; never the plaintext.
    :param scopes: granted permission scopes («области доступа»).
    :param created_at: issue time as a wall-clock epoch second.
    :param expires_at: optional expiry epoch second; ``None`` means non-expiring.
    """

    key_id: str
    prefix: str
    key_hash: str
    scopes: frozenset[str]
    created_at: float
    expires_at: float | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a serializable, log-safe view; never carries the plaintext."""
        data = asdict(self)
        data["scopes"] = sorted(self.scopes)
        return data


def _hash_plaintext(plaintext: str) -> str:
    """Return the lowercase hex SHA-256 digest of *plaintext*."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def generate_api_key(
    raw: bytes,
    *,
    key_id: str,
    scopes: frozenset[str],
    created_at: float,
    expires_at: float | None = None,
    prefix: str = "sk_",
) -> tuple[str, ApiKeyRecord]:
    """Mint an API key from raw entropy *raw* (§19.2).

    Deterministic for a fixed ``(raw, prefix)`` pair: the plaintext is
    ``prefix + base32(raw)`` (RFC 4648 base32, uppercase) and ``key_hash`` is the
    SHA-256 hex of that plaintext. Returns ``(plaintext, record)``; the caller is
    responsible for handing the plaintext to the client exactly once and
    persisting only the returned :class:`ApiKeyRecord`.
    """
    plaintext = prefix + base64.b32encode(raw).decode("ascii")
    record = ApiKeyRecord(
        key_id=key_id,
        prefix=prefix,
        key_hash=_hash_plaintext(plaintext),
        scopes=frozenset(scopes),
        created_at=created_at,
        expires_at=expires_at,
    )
    return plaintext, record


def verify_api_key(plaintext: str, record: ApiKeyRecord) -> bool:
    """Return True iff *plaintext* matches *record* (§19.2).

    Recomputes the SHA-256 digest over *plaintext* and compares it against
    ``record.key_hash`` in constant time. Never raises.
    """
    presented = _hash_plaintext(plaintext)
    return hmac.compare_digest(presented, record.key_hash)


def is_expired(record: ApiKeyRecord, now: float) -> bool:
    """Return True iff *record* has an expiry that is at or before *now* (§19.2).

    A record with ``expires_at is None`` never expires and returns ``False``.
    """
    if record.expires_at is None:
        return False
    return now >= record.expires_at
