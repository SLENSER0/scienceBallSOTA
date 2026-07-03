"""Offline breached-password detection — оффлайн-проверка утёкших паролей (§19.2 Auth).

This module layers *breach* / *pwned* detection on top of the complexity-only
:mod:`kg_common.security.password_policy`. It is deliberately **network-free**:
the caller performs the HIBP-style k-anonymity range request out of band and
hands us the resulting ``suffix → count`` mapping «отображение хвост → счётчик».
We never open a socket.

The HIBP «Pwned Passwords» range API works on a *k-anonymity* split of the
SHA-1 hash: the client sends only the first 5 hex characters (the *prefix*) and
receives every 35-character *suffix* seen for that prefix together with its
breach count. :func:`sha1_prefix` reproduces that split locally, and
:func:`check_password` matches a candidate's suffix against a caller-supplied
mapping. A small module-level :data:`COMMON_PASSWORDS` blocklist short-circuits
the very weakest passwords «самые частые пароли» before any range lookup.

Every function is pure-python with no third-party dependency.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Where a breach verdict originated («источник вердикта»).
SOURCE_RANGE = "range"
SOURCE_BLOCKLIST = "blocklist"
SOURCE_CLEAN = "clean"

# Length of the k-anonymity hash prefix sent to the range API («длина префикса»).
_PREFIX_LEN = 5

# A small local blocklist of the most common passwords («частые пароли»).
# Stored lowercase; :func:`is_common` compares case-insensitively.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "123456",
        "123456789",
        "12345678",
        "12345",
        "1234567",
        "qwerty",
        "abc123",
        "password1",
        "111111",
        "123123",
        "admin",
        "letmein",
        "welcome",
        "monkey",
        "iloveyou",
        "1234567890",
        "qwerty123",
        "000000",
        "dragon",
    }
)


def sha1_prefix(password: str) -> tuple[str, str]:
    """Split *password*'s SHA-1 into a k-anonymity ``(prefix, suffix)`` pair (§19.2).

    Returns the uppercase-hex SHA-1 digest cut into a 5-character *prefix* and a
    35-character *suffix* «префикс и хвост», exactly as the HIBP range API expects.
    Concatenating the two reproduces the full 40-character digest.
    """
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    return digest[:_PREFIX_LEN], digest[_PREFIX_LEN:]


@dataclass(frozen=True)
class BreachResult:
    """Outcome of a breached-password check (§19.2 Auth).

    ``breached`` is ``True`` when the password was found in the blocklist or in the
    range mapping; ``count`` is the breach occurrence count (``0`` when clean);
    ``source`` is one of :data:`SOURCE_RANGE`, :data:`SOURCE_BLOCKLIST`,
    :data:`SOURCE_CLEAN` «источник вердикта».
    """

    breached: bool
    count: int
    source: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the result («словарь для сериализации»)."""
        return {
            "breached": self.breached,
            "count": self.count,
            "source": self.source,
        }


def is_common(password: str) -> bool:
    """True if *password* is in the local :data:`COMMON_PASSWORDS` blocklist (§19.2).

    The comparison is case-insensitive «без учёта регистра»; the blocklist itself is
    stored lowercase.
    """
    return password.lower() in COMMON_PASSWORDS


def check_password(password: str, suffix_counts: Mapping[str, int]) -> BreachResult:
    """Check *password* for breach exposure, blocklist first then range (§19.2 Auth).

    Evaluation order «порядок проверки»:

    1. If *password* is in the local blocklist, short-circuit with
       :data:`SOURCE_BLOCKLIST` (count ``0`` — the blocklist carries no count).
    2. Otherwise split the SHA-1 and look its 35-char suffix up in *suffix_counts*
       (the caller's k-anonymity range response). A hit yields :data:`SOURCE_RANGE`
       with the mapped count; a miss yields :data:`SOURCE_CLEAN`.
    """
    if is_common(password):
        return BreachResult(breached=True, count=0, source=SOURCE_BLOCKLIST)

    _prefix, suffix = sha1_prefix(password)
    count = suffix_counts.get(suffix)
    if count is not None:
        return BreachResult(breached=True, count=count, source=SOURCE_RANGE)

    return BreachResult(breached=False, count=0, source=SOURCE_CLEAN)
