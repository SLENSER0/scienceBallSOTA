"""Argon2/bcrypt-free password hashing (§19.2 Auth).

Hash and verify user passwords («пароли пользователей») using nothing but the
Python standard library: PBKDF2-HMAC-SHA256 (:func:`hashlib.pbkdf2_hmac`). The
sibling :mod:`kg_common.security.password_policy` only *scores* password
strength — it never derives or stores a hash. This module fills that gap without
pulling in ``argon2`` or ``bcrypt``.

A frozen :class:`HashParams` captures the cost parameters (algorithm identifier,
iteration count, salt length). :func:`hash_password` derives a per-password
random salt and returns a single self-describing string in the shape::

    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

:func:`verify_password` re-derives the digest from a presented password and the
salt/iterations parsed out of the encoded string, comparing in constant time
(«постоянное время») via :func:`hmac.compare_digest`. :func:`needs_rehash`
reports whether a stored encoding was produced with weaker parameters than the
current policy, so callers can transparently upgrade on next login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

# Wire identifier for the only algorithm supported here («идентификатор алгоритма»).
ALGORITHM_PBKDF2_SHA256 = "pbkdf2_sha256"

# Underlying HMAC hash name handed to :func:`hashlib.pbkdf2_hmac`.
_HMAC_HASH_NAME = "sha256"

# Number of ``$``-separated fields in a valid encoded string («число полей»).
_ENCODED_FIELDS = 4


@dataclass(frozen=True)
class HashParams:
    """Immutable PBKDF2 cost parameters (§19.2 Auth).

    :param algorithm: wire algorithm identifier; only ``"pbkdf2_sha256"``.
    :param iterations: PBKDF2 iteration count («число итераций»); higher is slower.
    :param salt_bytes: length in bytes of the random per-password salt («длина соли»).
    """

    algorithm: str = ALGORITHM_PBKDF2_SHA256
    iterations: int = 200_000
    salt_bytes: int = 16

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the parameters («словарь для сериализации»)."""
        return {
            "algorithm": self.algorithm,
            "iterations": self.iterations,
            "salt_bytes": self.salt_bytes,
        }


def _b64encode(raw: bytes) -> str:
    """Return the padded standard-base64 text of *raw* («кодирование base64»)."""
    return base64.b64encode(raw).decode("ascii")


def _b64decode(text: str) -> bytes:
    """Return the bytes decoded from standard-base64 *text* («декодирование base64»)."""
    return base64.b64decode(text.encode("ascii"))


def _derive(pw: str, salt: bytes, iterations: int) -> bytes:
    """Derive the raw PBKDF2-HMAC-SHA256 digest for *pw* («вывод ключа»)."""
    return hashlib.pbkdf2_hmac(_HMAC_HASH_NAME, pw.encode("utf-8"), salt, iterations)


def hash_password(pw: str, params: HashParams = HashParams(), *, salt: bytes | None = None) -> str:
    """Hash *pw* under *params*, returning a self-describing encoding (§19.2).

    A fresh cryptographically random salt of ``params.salt_bytes`` bytes is drawn
    unless *salt* is supplied (the injection point exists for reproducible tests).
    The result is ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``; two calls
    with a random salt therefore differ «две подписи отличаются».
    """
    if salt is None:
        salt = os.urandom(params.salt_bytes)
    digest = _derive(pw, salt, params.iterations)
    return "$".join(
        (
            params.algorithm,
            str(params.iterations),
            _b64encode(salt),
            _b64encode(digest),
        )
    )


def verify_password(pw: str, encoded: str) -> bool:
    """Return True iff *pw* reproduces the digest inside *encoded* (§19.2).

    The salt and iteration count are parsed out of *encoded*, the digest is
    re-derived from *pw*, and the two digests are compared in constant time via
    :func:`hmac.compare_digest`. Any malformed or unsupported encoding, or a
    mismatched algorithm, yields ``False`` rather than raising «никогда не бросает».
    """
    parts = encoded.split("$")
    if len(parts) != _ENCODED_FIELDS:
        return False
    algorithm, iterations_text, salt_b64, hash_b64 = parts
    if algorithm != ALGORITHM_PBKDF2_SHA256:
        return False
    try:
        iterations = int(iterations_text)
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    if iterations <= 0:
        return False
    presented = _derive(pw, salt, iterations)
    return hmac.compare_digest(presented, expected)


def needs_rehash(encoded: str, params: HashParams) -> bool:
    """Return True iff *encoded* is weaker than *params* and should be re-hashed (§19.2).

    A rehash is advised when the stored algorithm differs, the stored iteration
    count is below ``params.iterations``, or the stored salt is shorter than
    ``params.salt_bytes``. A malformed encoding always warrants a rehash.
    """
    parts = encoded.split("$")
    if len(parts) != _ENCODED_FIELDS:
        return True
    algorithm, iterations_text, salt_b64, _hash_b64 = parts
    if algorithm != params.algorithm:
        return True
    try:
        iterations = int(iterations_text)
        salt = _b64decode(salt_b64)
    except (ValueError, TypeError):
        return True
    if iterations < params.iterations:
        return True
    return len(salt) < params.salt_bytes
