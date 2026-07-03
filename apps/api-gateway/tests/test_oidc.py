"""[DE] authentik OIDC token verification + group→role mapping (§19 / §24.14).

Simulates authentik by signing RS256 tokens with a local RSA key and injecting the
public key (the JWKS network fetch is bypassed via the ``key=`` seam). Covers
signature/issuer/audience/expiry verification, the group→role precedence, and the
opt-in fallback to the legacy demo path.
"""

from __future__ import annotations

import time

import jwt
import pytest
from api_gateway import auth, oidc
from cryptography.hazmat.primitives.asymmetric import rsa

import kg_common.config as cfg

_ISSUER = "https://idp.example.com/application/o/science-ball/"
_AUD = "science-ball-client"


@pytest.fixture
def rsa_key():  # type: ignore[no-untyped-def]
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc_on(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", _AUD)
    _clear_caches()
    yield
    _clear_caches()


def _clear_caches() -> None:
    cfg.get_settings.cache_clear()
    oidc._group_role_map.cache_clear()
    oidc._discover_jwks_url.cache_clear()


def _token(priv, *, groups=None, sub="u_alice", iss=_ISSUER, aud=_AUD, exp_delta=300, **extra):
    now = int(time.time())
    payload = {
        "sub": sub,
        "preferred_username": "alice",
        "email": "alice@example.com",
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_delta,
        "groups": groups if groups is not None else [],
        **extra,
    }
    return jwt.encode(payload, priv, algorithm="RS256")


# -- verification ----------------------------------------------------------
def test_valid_token_verifies(oidc_on, rsa_key) -> None:
    tok = _token(rsa_key, groups=["curator"])
    claims = oidc.verify_oidc_token(tok, key=rsa_key.public_key())
    assert claims is not None
    assert claims["preferred_username"] == "alice"
    assert claims["groups"] == ["curator"]


def test_wrong_audience_rejected(oidc_on, rsa_key) -> None:
    tok = _token(rsa_key, aud="some-other-client")
    assert oidc.verify_oidc_token(tok, key=rsa_key.public_key()) is None


def test_wrong_issuer_rejected(oidc_on, rsa_key) -> None:
    tok = _token(rsa_key, iss="https://evil.example.com/")
    assert oidc.verify_oidc_token(tok, key=rsa_key.public_key()) is None


def test_expired_token_rejected(oidc_on, rsa_key) -> None:
    tok = _token(rsa_key, exp_delta=-10)
    assert oidc.verify_oidc_token(tok, key=rsa_key.public_key()) is None


def test_wrong_signing_key_rejected(oidc_on, rsa_key) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tok = _token(rsa_key)
    assert oidc.verify_oidc_token(tok, key=other.public_key()) is None


def test_disabled_returns_none(rsa_key, monkeypatch) -> None:
    monkeypatch.setenv("OIDC_ENABLED", "false")
    _clear_caches()
    try:
        tok = _token(rsa_key)
        assert oidc.verify_oidc_token(tok, key=rsa_key.public_key()) is None
    finally:
        _clear_caches()


# -- group → role mapping --------------------------------------------------
def test_role_name_match_and_precedence(oidc_on) -> None:
    assert oidc.role_from_groups(["researcher", "admin"]) == "admin"  # strongest wins
    assert oidc.role_from_groups(["curator"]) == "curator"
    assert oidc.role_from_groups(["unmapped-group"]) == "researcher"  # default
    assert oidc.role_from_groups([]) == "researcher"


def test_explicit_group_role_map(monkeypatch) -> None:
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_GROUP_ROLE_MAP", '{"kg-admins": "admin", "kg-people": "researcher"}')
    _clear_caches()
    try:
        assert oidc.role_from_groups(["kg-people", "kg-admins"]) == "admin"
        assert oidc.role_from_groups(["kg-people"]) == "researcher"
    finally:
        _clear_caches()


def test_claims_to_identity(oidc_on) -> None:
    user, role = oidc.claims_to_identity(
        {"preferred_username": "bob", "sub": "u_bob", "groups": ["project_manager"]}
    )
    assert user == "bob" and role == "project_manager"
    # string groups claim is tolerated (single membership)
    _, role2 = oidc.claims_to_identity({"sub": "x", "groups": "admin"})
    assert role2 == "admin"


# -- integration with the auth dependencies --------------------------------
def test_current_role_uses_oidc_then_falls_back(oidc_on, rsa_key, monkeypatch) -> None:
    tok = _token(rsa_key, groups=["curator"])
    # inject the public key so no JWKS network call is made
    monkeypatch.setattr(oidc, "_signing_key", lambda _t: rsa_key.public_key())
    assert auth.current_role(authorization=f"Bearer {tok}") == "curator"
    user = auth.current_user(authorization=f"Bearer {tok}")
    assert user == "alice"


def test_demo_hs256_still_works_when_oidc_on(oidc_on) -> None:
    # a legacy HS256 demo token is NOT an authentik token → OIDC verify returns
    # None → the HS256 path still resolves it.
    tok = auth.issue_token("carol", "analyst")
    assert auth.current_role(authorization=f"Bearer {tok}") == "analyst"
    assert auth.current_user(authorization=f"Bearer {tok}") == "carol"


def test_public_config_shape(oidc_on) -> None:
    c = oidc.public_config()
    assert c["enabled"] is True
    assert c["authorization_endpoint"].endswith("/authorize/")
    assert "groups" in c["scopes"]


# -- labs + principal (source-access identity) -----------------------------
def test_labs_from_claims(oidc_on) -> None:
    # authentik lab:* groups → lab memberships for lab-restricted sources
    assert set(oidc.labs_from_claims({"groups": ["curator", "lab:lab_a", "lab:lab_b"]})) == {
        "lab_a",
        "lab_b",
    }
    # an explicit `labs` claim wins
    assert oidc.labs_from_claims({"groups": ["lab:x"], "labs": ["lab_z"]}) == ["lab_z"]
    assert oidc.labs_from_claims({"groups": ["admin"]}) == []


def test_current_principal_from_oidc(oidc_on, rsa_key, monkeypatch) -> None:
    tok = _token(rsa_key, groups=["curator", "lab:lab_a"])
    monkeypatch.setattr(oidc, "_signing_key", lambda _t: rsa_key.public_key())
    p = auth.current_principal(authorization=f"Bearer {tok}")
    assert p.user_id == "alice"
    assert p.roles == frozenset({"curator"})
    assert p.labs == frozenset({"lab_a"})


def test_current_principal_from_demo_and_headers(oidc_on) -> None:
    tok = auth.issue_token("dave", "analyst")
    p = auth.current_principal(authorization=f"Bearer {tok}")
    assert p.user_id == "dave" and p.roles == frozenset({"analyst"})
    # no token → dev header fallback
    p2 = auth.current_principal(authorization=None, x_role="curator", x_user_id="u_x")
    assert p2.user_id == "u_x" and p2.roles == frozenset({"curator"})
