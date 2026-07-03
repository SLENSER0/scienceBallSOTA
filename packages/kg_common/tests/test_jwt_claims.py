"""Tests for the structural JWT claims validator (§19.2 auth)."""

from __future__ import annotations

from kg_common.security.jwt_claims import (
    ClaimsVerdict,
    is_expired,
    remaining_ttl,
    validate_claims,
)

_KNOWN = frozenset({"reader", "curator", "admin"})


def _claims(now: float, **over: object) -> dict[str, object]:
    """A fully-formed valid claim set at *now*; override fields via kwargs."""
    base: dict[str, object] = {
        "sub": "user-1",
        "roles": ["reader", "curator"],
        "exp": now + 100.0,
        "iat": now - 10.0,
        "jti": "tok-1",
    }
    base.update(over)
    return base


def test_missing_sub_is_invalid() -> None:
    claims = _claims(1000.0)
    del claims["sub"]
    verdict = validate_claims(claims, now=1000.0, known_roles=_KNOWN)
    assert verdict.valid is False
    assert "missing:sub" in verdict.reasons


def test_hard_expired_is_invalid_and_flagged() -> None:
    claims = _claims(1000.0, exp=1000.0 - 100.0)
    verdict = validate_claims(claims, now=1000.0, known_roles=_KNOWN)
    assert verdict.expired is True
    assert verdict.valid is False
    assert "expired" in verdict.reasons


def test_is_expired_absorbs_leeway() -> None:
    # exp only 5s in the past but 30s leeway -> not yet expired.
    claims = _claims(1000.0, exp=1000.0 - 5.0)
    assert is_expired(claims, 1000.0, leeway=30.0) is False


def test_unknown_role_is_invalid() -> None:
    claims = _claims(1000.0, roles=["reader", "wizard"])
    verdict = validate_claims(claims, now=1000.0, known_roles=_KNOWN)
    assert verdict.valid is False
    assert any(r.startswith("unknown_role") for r in verdict.reasons)


def test_revoked_jti_is_invalid() -> None:
    claims = _claims(1000.0, jti="tok-bad")
    verdict = validate_claims(
        claims, now=1000.0, known_roles=_KNOWN, revoked_jti=frozenset({"tok-bad"})
    )
    assert verdict.valid is False
    assert "revoked" in verdict.reasons


def test_iat_in_future_is_invalid() -> None:
    claims = _claims(1000.0, iat=1000.0 + 100.0)
    verdict = validate_claims(claims, now=1000.0, known_roles=_KNOWN)
    assert verdict.valid is False
    assert "iat_in_future" in verdict.reasons


def test_fully_valid_claims() -> None:
    verdict = validate_claims(_claims(1000.0), now=1000.0, known_roles=_KNOWN)
    assert verdict.valid is True
    assert verdict.reasons == ()
    assert verdict.expired is False
    assert isinstance(verdict, ClaimsVerdict)
    assert verdict.as_dict() == {"valid": True, "reasons": [], "expired": False}


def test_remaining_ttl() -> None:
    claims = _claims(1000.0, exp=1000.0 + 100.0)
    assert remaining_ttl(claims, 1000.0) == 100.0
