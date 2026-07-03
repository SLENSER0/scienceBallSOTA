"""Single-use stream-token auth for SSE/WebSocket connections (§19.2 auth).

Browser ``EventSource`` and ``WebSocket`` clients cannot attach custom
``Authorization`` headers, so a long-lived session token must not travel on the
wire for every stream. Instead the server mints a short-lived, single-use
*stream token* («потоковый токен») bound to a specific ``(session_id, user_id)``
pair. The compact wire form is ``session.user.jti.exp.sig`` where ``sig`` is the
hex HMAC-SHA256 of the ``session.user.jti.exp`` payload keyed by a server secret.

:func:`verify` recomputes the HMAC in constant time («постоянное время»),
enforces expiry, checks the session/user binding, and guarantees single use by
tracking each ``jti`` in a caller-owned ``seen`` set — a replayed token whose
``jti`` is already present is rejected. Fields never carry the secret, so a
parsed :class:`StreamToken` is safe to log via :meth:`StreamToken.as_dict`.
"""

from __future__ import annotations

import hmac
from dataclasses import asdict, dataclass
from hashlib import sha256

_SEP = "."
_MIN_SEGMENTS = 5


@dataclass(frozen=True)
class StreamToken:
    """Immutable, parsed view of a stream token («потоковый токен»).

    :param session_id: session the token is bound to.
    :param user_id: user the token is bound to.
    :param jti: unique token id used for single-use replay defence.
    :param issued_at: mint time as a wall-clock epoch second.
    :param expires_at: expiry epoch second; the token is invalid at or after it.
    """

    session_id: str
    user_id: str
    jti: str
    issued_at: float
    expires_at: float

    def as_dict(self) -> dict[str, object]:
        """Return a serializable, log-safe view; never carries the secret/sig."""
        return asdict(self)


def _payload(session_id: str, user_id: str, jti: str, expires_at: float) -> str:
    """Return the canonical signing payload ``session.user.jti.exp``."""
    return _SEP.join((session_id, user_id, jti, repr(expires_at)))


def _sign(secret: str, payload: str) -> str:
    """Return the lowercase hex HMAC-SHA256 of *payload* keyed by *secret*."""
    return hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()


def mint(
    secret: str,
    session_id: str,
    user_id: str,
    jti: str,
    issued_at: float,
    ttl_sec: float,
) -> str:
    """Mint a compact ``session.user.jti.exp.sig`` stream token (§19.2).

    The expiry is ``issued_at + ttl_sec`` and ``sig`` is the hex HMAC-SHA256 of
    the ``session.user.jti.exp`` payload. Segments must not contain the ``.``
    separator, else the round-trip through :func:`parse` would be ambiguous.
    """
    for part in (session_id, user_id, jti):
        if _SEP in part:
            msg = f"stream-token segment must not contain {_SEP!r}: {part!r}"
            raise ValueError(msg)
    expires_at = issued_at + ttl_sec
    payload = _payload(session_id, user_id, jti, expires_at)
    sig = _sign(secret, payload)
    return _SEP.join((payload, sig))


def parse(token: str) -> StreamToken:
    """Parse a wire token into a :class:`StreamToken` (§19.2).

    Raises :class:`ValueError` on a malformed token: too few segments or a
    non-numeric expiry. This does **not** verify the HMAC — use :func:`verify`.
    The float ``exp`` may itself contain ``.``; ``session``/``user``/``jti`` are
    dot-free by construction and ``sig`` is dot-free hex, so the expiry is the
    join of the middle segments.
    """
    parts = token.split(_SEP)
    if len(parts) < _MIN_SEGMENTS:
        msg = f"malformed stream token: expected >={_MIN_SEGMENTS} segments, got {len(parts)}"
        raise ValueError(msg)
    session_id, user_id, jti = parts[0], parts[1], parts[2]
    exp_raw = _SEP.join(parts[3:-1])
    try:
        expires_at = float(exp_raw)
    except ValueError as exc:
        msg = f"malformed stream token: bad expiry {exp_raw!r}"
        raise ValueError(msg) from exc
    return StreamToken(
        session_id=session_id,
        user_id=user_id,
        jti=jti,
        issued_at=0.0,
        expires_at=expires_at,
    )


def verify(
    secret: str,
    token: str,
    *,
    session_id: str,
    user_id: str,
    now: float,
    seen: set[str],
) -> StreamToken:
    """Verify *token* and consume its ``jti`` for single use (§19.2).

    Checks, in order: the HMAC signature in constant time, expiry against *now*,
    the ``(session_id, user_id)`` binding, and replay via *seen*. On success the
    ``jti`` is added to *seen* and the parsed :class:`StreamToken` is returned.
    Raises :class:`ValueError` on any failure; *seen* is left untouched then.
    """
    parts = token.split(_SEP)
    if len(parts) < _MIN_SEGMENTS:
        msg = f"malformed stream token: expected >={_MIN_SEGMENTS} segments, got {len(parts)}"
        raise ValueError(msg)
    payload = _SEP.join(parts[:-1])
    presented_sig = parts[-1]
    expected_sig = _sign(secret, payload)
    if not hmac.compare_digest(presented_sig, expected_sig):
        raise ValueError("stream token signature mismatch")
    parsed = parse(token)
    if now >= parsed.expires_at:
        raise ValueError("stream token expired")
    if parsed.session_id != session_id:
        raise ValueError("stream token session_id mismatch")
    if parsed.user_id != user_id:
        raise ValueError("stream token user_id mismatch")
    if parsed.jti in seen:
        raise ValueError("stream token replay detected")
    seen.add(parsed.jti)
    return parsed
