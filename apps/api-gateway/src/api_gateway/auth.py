"""JWT auth + role resolution (§19 / §24.14).

Two token paths, resolved from ``Authorization: Bearer <jwt>``:

* **authentik OIDC** (production SSO, opt-in via ``Settings.oidc_enabled``) — an
  RS256 access/ID token verified against the provider's JWKS, whose ``groups``
  claim maps to a platform :class:`~kg_schema.enums.Role` (see
  :mod:`api_gateway.oidc`).
* **demo HS256** (local/dev) — issued by ``/auth/login`` and signed with the
  local ``JWT_SECRET``, carrying the role directly.

OIDC is tried first when enabled; both fall back to the ``X-Role`` header (dev) or
``researcher``. The RBAC enforcement downstream is identical either way.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Header

from api_gateway.oidc import claims_to_identity, labs_from_claims, verify_oidc_token
from kg_common import get_settings
from kg_common.security.clearance import principal_from
from kg_common.security.source_access import Principal
from kg_schema.enums import Role

VALID_ROLES = {str(r) for r in Role}


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def issue_token(username: str, role: str) -> str:
    s = get_settings()
    if role not in VALID_ROLES:
        role = str(Role.RESEARCHER)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + s.jwt_ttl_minutes * 60,
    }
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def current_role(
    authorization: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
) -> str:
    """Resolve caller role: authentik OIDC → demo HS256 → X-Role (dev) → researcher."""
    token = _bearer(authorization)
    if token:
        oidc = verify_oidc_token(token)  # None when OIDC off / not an authentik token
        if oidc:
            return claims_to_identity(oidc)[1]
        claims = decode_token(token)
        if claims and claims.get("role") in VALID_ROLES:
            return claims["role"]
    if x_role in VALID_ROLES:
        return x_role
    return str(Role.RESEARCHER)


def current_user(authorization: str | None = Header(default=None)) -> str:
    token = _bearer(authorization)
    if token:
        oidc = verify_oidc_token(token)
        if oidc:
            return claims_to_identity(oidc)[0]
        claims = decode_token(token)
        if claims:
            return str(claims.get("sub", "anonymous"))
    return "anonymous"


def current_principal(
    authorization: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> Principal:
    """The acting principal (user + role + labs) used for source-access filtering.

    Same token cascade as :func:`current_role` — authentik OIDC (roles + ``lab:*``
    group memberships) first, then the demo HS256 token, then dev headers. The
    resulting :class:`Principal` drives per-source ACLs and the access-level
    clearance (see :mod:`kg_common.security.clearance`).
    """
    token = _bearer(authorization)
    if token:
        oidc = verify_oidc_token(token)
        if oidc:
            user, role = claims_to_identity(oidc)
            return principal_from(user, role, labs_from_claims(oidc))
        claims = decode_token(token)
        if claims:
            role = claims.get("role") if claims.get("role") in VALID_ROLES else str(Role.RESEARCHER)
            return principal_from(str(claims.get("sub", "anonymous")), role, [])
    role = x_role if x_role in VALID_ROLES else str(Role.RESEARCHER)
    return principal_from(x_user_id or "anonymous", role, [])
