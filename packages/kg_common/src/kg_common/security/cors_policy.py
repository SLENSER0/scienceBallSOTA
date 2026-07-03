"""CORS allowlist resolver for transport hardening (§19.7 secrets/transport).

A :class:`CorsPolicy` declares which browser *origins* may call the API, plus
the methods/headers/credentials allowed on the cross-origin request. The policy
is **fail-closed** («по умолчанию закрыто»): a wildcard ``'*'`` origin combined
with ``allow_credentials`` is rejected at construction time, because echoing
``Access-Control-Allow-Credentials: true`` alongside ``*`` is forbidden by the
CORS spec and would let any site read authenticated responses.

:func:`resolve_cors` takes a request ``Origin`` and returns a :class:`CorsDecision`
carrying the exact ``Access-Control-*`` response headers. A listed origin is
echoed back verbatim; a non-credentialed wildcard policy answers ``'*'``; an
unlisted origin yields ``allowed=False`` with **no** headers («ничего не отдаём»).
Pure-python, frozen dataclasses — no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Wildcard origin token («любой источник»).
_WILDCARD = "*"

# Default cross-origin methods and headers («методы и заголовки по умолчанию»).
_DEFAULT_METHODS: tuple[str, ...] = ("GET", "POST", "PATCH", "DELETE", "OPTIONS")
_DEFAULT_HEADERS: tuple[str, ...] = ("Authorization", "Content-Type")


@dataclass(frozen=True)
class CorsPolicy:
    """Immutable CORS allowlist policy (§19.7).

    ``allowed_origins`` — exact origins (scheme://host[:port]) or ``{'*'}`` for
    any origin. ``allow_credentials`` may not combine with ``'*'`` (fail-closed).
    ``max_age`` is the preflight cache lifetime in seconds.
    """

    allowed_origins: frozenset[str]
    allow_credentials: bool = False
    allowed_methods: tuple[str, ...] = _DEFAULT_METHODS
    allowed_headers: tuple[str, ...] = _DEFAULT_HEADERS
    max_age: int = 600

    def __post_init__(self) -> None:
        """Reject the unsafe wildcard-plus-credentials combination («небезопасно»)."""
        if _WILDCARD in self.allowed_origins and self.allow_credentials:
            raise ValueError(
                "CORS wildcard origin '*' cannot be combined with allow_credentials "
                "(«'*' несовместим с учётными данными»)"
            )

    @property
    def is_wildcard(self) -> bool:
        """True if this policy admits any origin («разрешён любой источник»)."""
        return _WILDCARD in self.allowed_origins

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the policy («словарь для сериализации»)."""
        return {
            "allowed_origins": sorted(self.allowed_origins),
            "allow_credentials": self.allow_credentials,
            "allowed_methods": list(self.allowed_methods),
            "allowed_headers": list(self.allowed_headers),
            "max_age": self.max_age,
        }


@dataclass(frozen=True)
class CorsDecision:
    """Outcome of a CORS check for one request origin (§19.7).

    ``allowed`` says whether the origin passed the allowlist; ``headers`` holds the
    ``Access-Control-*`` response headers to emit (empty when disallowed).
    """

    allowed: bool
    headers: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the decision («словарь для сериализации»)."""
        return {"allowed": self.allowed, "headers": dict(self.headers)}


def resolve_cors(policy: CorsPolicy, origin: str) -> CorsDecision:
    """Resolve *origin* against *policy*, returning a :class:`CorsDecision` (§19.7).

    A listed origin is echoed in ``Access-Control-Allow-Origin``; a non-credentialed
    wildcard policy answers ``'*'``. An unlisted origin returns ``allowed=False`` with
    no headers («неизвестный источник — пустой ответ»). When credentials are allowed
    the concrete origin is always echoed (never ``'*'``) plus the credentials header.
    """
    is_listed = origin in policy.allowed_origins
    if policy.is_wildcard and not policy.allow_credentials:
        allow_origin = _WILDCARD
    elif is_listed:
        allow_origin = origin
    else:
        return CorsDecision(allowed=False, headers={})

    headers: dict[str, str] = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Methods": ", ".join(policy.allowed_methods),
        "Access-Control-Allow-Headers": ", ".join(policy.allowed_headers),
        "Access-Control-Max-Age": str(policy.max_age),
    }
    if policy.allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    if allow_origin != _WILDCARD:
        # Vary on Origin so caches don't serve one origin's response to another.
        headers["Vary"] = "Origin"
    return CorsDecision(allowed=True, headers=headers)
