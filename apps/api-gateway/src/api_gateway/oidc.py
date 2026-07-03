"""OIDC (authentik) token verification + group→role mapping (§19 / §24.14).

The gateway's demo login issues HS256 tokens (see :mod:`api_gateway.auth`); a real
deployment plugs in an Identity Provider. This module makes the gateway accept
**OIDC access/ID tokens issued by authentik**: it verifies the RS256 signature
against the provider's JWKS (discovered from the issuer), checks issuer / audience
/ expiry, and maps the token's ``groups`` claim onto one of the platform's
:class:`~kg_schema.enums.Role` values. Everything is opt-in
(``Settings.oidc_enabled``); when off, or on any verification failure, the caller
falls back to the legacy demo path — nothing here runs at import time and no
network call happens unless OIDC is enabled and a Bearer token is presented.
"""

from __future__ import annotations

import functools
import json
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from kg_common import get_logger, get_settings
from kg_schema.enums import Role

_log = get_logger("api.oidc")

# Highest-privilege first: when a user is in several mapped groups, the strongest
# role wins. ``external_partner`` is the most restricted principal.
_ROLE_PRECEDENCE: tuple[Role, ...] = (
    Role.ADMIN,
    Role.PROJECT_MANAGER,
    Role.CURATOR,
    Role.ANALYST,
    Role.RESEARCHER,
    Role.EXTERNAL_PARTNER,
)
_VALID_ROLES = {str(r) for r in Role}


def oidc_enabled() -> bool:
    return bool(get_settings().oidc_enabled)


@functools.lru_cache(maxsize=4)
def _discover_jwks_url(issuer: str, override: str) -> str | None:
    """Resolve the JWKS URL: explicit override, else OIDC discovery on the issuer."""
    if override:
        return override
    if not issuer:
        return None
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        return resp.json().get("jwks_uri")
    except Exception as exc:  # network / provider down → no verification possible
        _log.warning("oidc.discovery_failed", url=url, error=str(exc))
        return None


@functools.lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    # PyJWKClient caches fetched keys internally and refreshes on unknown kid.
    return PyJWKClient(jwks_url)


def _signing_key(token: str) -> Any:
    """Fetch the RSA public key for ``token`` from the provider's JWKS (or None)."""
    s = get_settings()
    jwks_url = _discover_jwks_url(s.oidc_issuer, s.oidc_jwks_url)
    if not jwks_url:
        return None
    try:
        return _jwk_client(jwks_url).get_signing_key_from_jwt(token).key
    except Exception as exc:
        _log.warning("oidc.signing_key_failed", error=str(exc))
        return None


def verify_oidc_token(token: str, *, key: Any = None) -> dict[str, Any] | None:
    """Verify an authentik OIDC token; return its claims or ``None``.

    Checks the RS256 signature (against ``key`` if given, else the provider's
    JWKS), the issuer, the audience (when configured) and expiry. Any failure —
    disabled, unverifiable, wrong issuer/audience, expired — yields ``None`` so the
    caller falls back to the legacy path. ``key`` is an injection seam for tests.
    """
    if not oidc_enabled() or not token:
        return None
    s = get_settings()
    signing_key = key if key is not None else _signing_key(token)
    if signing_key is None:
        return None
    options = {"require": ["exp"], "verify_aud": bool(s.oidc_audience)}
    try:
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=s.oidc_audience or None,
            issuer=s.oidc_issuer or None,
            options=options,
        )
    except jwt.PyJWTError as exc:
        _log.info("oidc.verify_rejected", error=str(exc))
        return None


@functools.lru_cache(maxsize=1)
def _group_role_map(raw: str) -> dict[str, str]:
    """Parse the configured authentik-group → platform-role JSON map (or empty)."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return {str(k): str(v) for k, v in parsed.items() if str(v) in _VALID_ROLES}
    except (json.JSONDecodeError, AttributeError) as exc:
        _log.warning("oidc.group_role_map_invalid", error=str(exc))
        return {}


def role_from_groups(groups: list[str]) -> str:
    """Map a user's authentik groups to the strongest platform role.

    Resolution: an explicit ``OIDC_GROUP_ROLE_MAP`` (group→role) if configured,
    else a group whose name equals a ``Role`` value (``curator`` → ``curator``).
    Among all matches the highest-privilege role wins; no match → ``researcher``.
    """
    s = get_settings()
    explicit = _group_role_map(s.oidc_group_role_map)
    matched: set[str] = set()
    for g in groups:
        name = str(g)
        if name in explicit:
            matched.add(explicit[name])
        elif name in _VALID_ROLES:
            matched.add(name)
    for role in _ROLE_PRECEDENCE:
        if str(role) in matched:
            return str(role)
    return str(Role.RESEARCHER)


def claims_to_identity(claims: dict[str, Any]) -> tuple[str, str]:
    """Map verified OIDC claims to ``(user, role)`` for the RBAC layer."""
    user = (
        claims.get("preferred_username") or claims.get("email") or claims.get("sub") or "anonymous"
    )
    groups_claim = get_settings().oidc_groups_claim
    groups = claims.get(groups_claim) or []
    if isinstance(groups, str):
        groups = [groups]
    return str(user), role_from_groups(list(groups))


def public_config() -> dict[str, Any]:
    """The non-secret OIDC config a SPA needs to start the Authorization-Code+PKCE
    flow against authentik (safe to expose)."""
    s = get_settings()
    issuer = s.oidc_issuer.rstrip("/")
    return {
        "enabled": bool(s.oidc_enabled),
        "issuer": s.oidc_issuer,
        "client_id": s.oidc_client_id,
        "redirect_uri": s.oidc_redirect_uri,
        "scopes": ["openid", "profile", "email", "groups"],
        "authorization_endpoint": f"{issuer}/authorize/" if issuer else "",
        "token_endpoint": f"{issuer}/token/" if issuer else "",
        "userinfo_endpoint": f"{issuer}/userinfo/" if issuer else "",
        "end_session_endpoint": f"{issuer}/end-session/" if issuer else "",
    }
