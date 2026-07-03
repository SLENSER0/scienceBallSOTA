"""Structural JWT claims validator (§19.2 auth).

While :mod:`kg_common.security.jwt_keyset` only *selects* signing / verification
keys by ``kid``, this module validates the decoded **claim set** itself
(«проверка набора утверждений»): required fields are present, the token is not
expired, ``iat`` is not implausibly in the future, every role is known and the
``jti`` is not revoked. No signature checking here — this is a pure, hand-check
able policy layer that runs *after* cryptographic verification.

Времена в секундах эпохи. :func:`validate_claims` returns a frozen
:class:`ClaimsVerdict` collecting *all* failure reasons (not just the first) so a
caller can log the full picture. :func:`is_expired` and :func:`remaining_ttl`
are small helpers over the ``exp`` claim with configurable ``leeway`` («допуск»).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ClaimsVerdict:
    """Outcome of :func:`validate_claims` («вердикт по утверждениям»).

    ``valid`` is the overall verdict, ``reasons`` collects every failure code
    (empty tuple when valid) and ``expired`` flags the ``exp``-specific failure
    so callers can distinguish "token aged out" from other policy breaches.
    """

    valid: bool
    reasons: tuple[str, ...]
    expired: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-ready mapping («сериализация в словарь»)."""
        return {
            "valid": self.valid,
            "reasons": list(self.reasons),
            "expired": self.expired,
        }


def is_expired(claims: Mapping[str, Any], now: float, leeway: float = 0.0) -> bool:
    """True if ``exp`` is at or before ``now - leeway`` («истёк с допуском»).

    A missing or non-numeric ``exp`` is treated as expired (fail closed).
    """
    exp = _as_float(claims.get("exp"))
    if exp is None:
        return True
    return exp <= now - leeway


def remaining_ttl(claims: Mapping[str, Any], now: float) -> float:
    """Seconds left until ``exp`` («остаток времени жизни»); may be negative.

    Returns ``0.0`` when ``exp`` is missing or non-numeric.
    """
    exp = _as_float(claims.get("exp"))
    if exp is None:
        return 0.0
    return exp - now


def validate_claims(
    claims: Mapping[str, Any],
    *,
    now: float,
    known_roles: frozenset[str],
    revoked_jti: frozenset[str] = frozenset(),
    leeway: float = 30.0,
    required: tuple[str, ...] = ("sub", "roles", "exp", "iat", "jti"),
) -> ClaimsVerdict:
    """Validate a decoded claim set against policy («проверка утверждений»).

    Collects *all* failures into :class:`ClaimsVerdict.reasons`:

    * ``missing:<name>`` — a required claim is absent (value ``None`` counts).
    * ``expired`` — ``exp`` is at or before ``now - leeway``.
    * ``iat_in_future`` — ``iat`` is more than ``leeway`` seconds ahead of ``now``.
    * ``unknown_role:<role>`` — a role not in ``known_roles``.
    * ``revoked`` — ``jti`` is listed in ``revoked_jti``.

    ``leeway`` («допуск») absorbs small clock skew for both ``exp`` and ``iat``.
    """
    reasons: list[str] = []

    for name in required:
        if claims.get(name) is None:
            reasons.append(f"missing:{name}")

    expired = False
    exp_present = "exp" not in required or claims.get("exp") is not None
    if exp_present and is_expired(claims, now, leeway):
        expired = True
        reasons.append("expired")

    iat = _as_float(claims.get("iat"))
    if iat is not None and iat > now + leeway:
        reasons.append("iat_in_future")

    roles = claims.get("roles")
    if roles is not None:
        for role in roles:
            if role not in known_roles:
                reasons.append(f"unknown_role:{role}")

    jti = claims.get("jti")
    if jti is not None and jti in revoked_jti:
        reasons.append("revoked")

    return ClaimsVerdict(valid=not reasons, reasons=tuple(reasons), expired=expired)


def _as_float(value: Any) -> float | None:
    """Best-effort numeric coercion; ``None`` on failure («мягкое приведение»)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
