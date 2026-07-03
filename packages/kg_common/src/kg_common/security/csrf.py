"""CSRF double-submit token issuance/verification (§19.7 transport hardening).

Stateless anti-CSRF protection via a signed double-submit token
(«двойная отправка токена»): a token carries its issue time and an HMAC-SHA256
that binds the *session id* and *issue time* to a server-side secret. The token
is echoed in both a cookie and a request header/field; the server recomputes the
HMAC and compares it in constant time. No token store is required.

Token wire format: ``"<issued_at_int>.<hexhmac>"`` — a decimal integer second
timestamp, a dot, then the lowercase hex HMAC digest. Verification enforces both
session binding (the presented session id must match the signed one) and a TTL
(«истечение срока»). :func:`issue_token` is deterministic for a fixed
``(secret, session_id, issued_at)`` triple. :class:`CsrfConfig.as_dict` never
emits the raw secret — only a stable masked fingerprint.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

# Marker («маска») substituted for the raw secret in :meth:`CsrfConfig.as_dict`.
_MASK = "***"


@dataclass(frozen=True)
class CsrfConfig:
    """Immutable CSRF signing config («конфиг подписи»).

    :param secret: server-side HMAC key; never serialized in the clear.
    :param ttl_sec: token lifetime in seconds; older tokens fail verification.
    """

    secret: bytes
    ttl_sec: float = 3600.0

    def _fingerprint(self) -> str:
        """Stable, non-reversible secret fingerprint for logs («отпечаток»)."""
        digest = hashlib.sha256(self.secret).hexdigest()
        return f"{_MASK}{digest[:8]}"

    def as_dict(self) -> dict[str, object]:
        """Return a log-safe view; the raw secret is masked, never emitted (§19.7)."""
        return {"secret": self._fingerprint(), "ttl_sec": self.ttl_sec}


def _sign(cfg: CsrfConfig, session_id: str, issued_at: int) -> str:
    """Compute the lowercase hex HMAC binding *session_id* + *issued_at*."""
    message = f"{session_id}.{issued_at}".encode()
    return hmac.new(cfg.secret, message, hashlib.sha256).hexdigest()


def issue_token(cfg: CsrfConfig, session_id: str, now: float) -> str:
    """Issue a signed CSRF token for *session_id* at time *now* (§19.7).

    Deterministic for a fixed ``(secret, session_id, int(now))`` triple. The
    returned token is ``"<issued_at_int>.<hexhmac>"``.
    """
    issued_at = int(now)
    signature = _sign(cfg, session_id, issued_at)
    return f"{issued_at}.{signature}"


def verify_token(cfg: CsrfConfig, session_id: str, token: str, now: float) -> bool:
    """Return True iff *token* is valid for *session_id* at time *now* (§19.7).

    Enforces (a) well-formedness, (b) constant-time signature match binding the
    session id, and (c) the TTL window ``0 <= now - issued_at <= ttl_sec``. Any
    malformed token or failed check returns ``False`` — never raises.
    """
    issued_str, sep, signature = token.partition(".")
    if not sep or not signature:
        return False
    try:
        issued_at = int(issued_str)
    except ValueError:
        return False

    expected = _sign(cfg, session_id, issued_at)
    if not hmac.compare_digest(expected, signature):
        return False

    age = now - issued_at
    return 0.0 <= age <= cfg.ttl_sec
