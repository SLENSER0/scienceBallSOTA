"""OIDC token verification + group→role mapping for authentik SSO (§19).

When ``OIDC_ISSUER`` is configured the gateway also trusts RS256 tokens issued by
an external identity provider (authentik). Tokens are validated against the
issuer's JWKS (fetched once and cached), and the token's ``groups`` claim is
mapped onto the app's RBAC :class:`~kg_schema.enums.Role` set. The demo HS256
login (``auth.issue_token``) keeps working as a local fallback — this module is
additive and inert until ``OIDC_ISSUER`` is set.

authentik group names map to roles by a small, explicit table; an unknown group
falls back to the least-privileged ``external_partner`` so a mis-configured IdP
never silently grants elevated access.
"""

from __future__ import annotations

import contextlib
import json
import urllib.request
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from kg_common import get_settings
from kg_schema.enums import Role

VALID_ROLES = {str(r) for r in Role}

# authentik/OIDC group name → RBAC role. Case-insensitive on the group side.
GROUP_ROLE_MAP: dict[str, str] = {
    "science-ball-admins": str(Role.ADMIN),
    "science-ball-curators": str(Role.CURATOR),
    "science-ball-researchers": str(Role.RESEARCHER),
    "science-ball-analysts": str(Role.ANALYST),
    "science-ball-managers": str(Role.PROJECT_MANAGER),
    "science-ball-partners": str(Role.EXTERNAL_PARTNER),
    # bare role names (a group literally named after the role) also resolve
    **{str(r): str(r) for r in Role},
}

# Highest-privilege-wins order when a token carries several mapped groups.
_ROLE_RANK = {
    str(Role.ADMIN): 5,
    str(Role.PROJECT_MANAGER): 4,
    str(Role.CURATOR): 3,
    str(Role.ANALYST): 2,
    str(Role.RESEARCHER): 1,
    str(Role.EXTERNAL_PARTNER): 0,
}


def oidc_enabled() -> bool:
    """True when an OIDC issuer is configured (SSO active)."""
    return bool(get_settings().oidc_issuer)


def role_for_groups(groups: list[str]) -> str:
    """Map OIDC group names to the highest-privilege RBAC role they grant.

    Unknown/empty → ``external_partner`` (least privilege), so a token from a
    correctly-authenticated but un-grouped user cannot see restricted data.
    """
    roles = [GROUP_ROLE_MAP[g.lower()] for g in groups if g.lower() in GROUP_ROLE_MAP]
    if not roles:
        return str(Role.EXTERNAL_PARTNER)
    return max(roles, key=lambda r: _ROLE_RANK.get(r, 0))


@lru_cache(maxsize=4)
def _discovery(issuer: str) -> dict[str, Any]:
    """Cached OIDC discovery document for the issuer."""
    disc = issuer.rstrip("/") + "/.well-known/openid-configuration"
    with urllib.request.urlopen(disc, timeout=5) as resp:
        return json.loads(resp.read().decode())


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> PyJWKClient:
    """Cached JWKS client from the issuer's discovery document."""
    return PyJWKClient(_discovery(issuer)["jwks_uri"])


def verify_oidc_token(token: str) -> dict[str, Any] | None:
    """Validate an authentik RS256 token; return its claims or ``None``.

    Never raises — an invalid/foreign token simply yields ``None`` so the caller
    can fall through to the dev HS256 path.
    """
    s = get_settings()
    if not s.oidc_issuer:
        return None
    try:
        signing_key = _jwks_client(s.oidc_issuer).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=s.oidc_audience,
            issuer=s.oidc_issuer.rstrip("/"),
            options={"verify_aud": bool(s.oidc_audience)},
        )
    except Exception:
        return None


def claims_to_identity(claims: dict[str, Any]) -> tuple[str, str]:
    """Extract ``(username, role)`` from validated OIDC claims."""
    user = str(claims.get("preferred_username") or claims.get("sub") or "sso-user")
    groups = claims.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    role = role_for_groups([str(g) for g in groups])
    return user, role


def public_oidc_config() -> dict[str, Any]:
    """Front-end-safe OIDC descriptor for building the authorize redirect."""
    s = get_settings()
    if not s.oidc_issuer:
        return {"enabled": False}
    # Prefer the issuer's real authorization_endpoint (from discovery); fall back
    # to the conventional authentik path if discovery is briefly unreachable.
    authorize = s.oidc_issuer.rstrip("/") + "/authorize/"
    with contextlib.suppress(Exception):  # descriptor is best-effort
        authorize = _discovery(s.oidc_issuer).get("authorization_endpoint", authorize)
    return {
        "enabled": True,
        "issuer": s.oidc_issuer,
        "client_id": s.oidc_client_id,
        "authorize_url": authorize,
        "scopes": "openid profile email groups",
    }
