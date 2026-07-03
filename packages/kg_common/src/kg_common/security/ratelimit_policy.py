"""Endpoint tier classification + limit-key policy for rate limiting (§19.4).

The token bucket in ``ratelimit.py`` / ``rate_limit_config.py`` is keyed by role,
but it does not know *which* endpoints deserve tighter limits nor *what* to key a
bucket on. This module fills that gap with two pure decisions:

* :func:`endpoint_tier` maps a ``(method, path)`` pair to a tier name — ``'auth'``
  for anything under ``/auth/`` (login/refresh are brute-force targets), ``'heavy'``
  for expensive writes/searches (chat messages, hybrid search, graph query, gap
  scan, uploads, ingest jobs), and ``'light'`` for everything else («всё
  остальное»).
* :func:`rate_limit_key` chooses the bucket key: auth traffic and anonymous
  requests are keyed by client IP (``'ip:'+ip``) so an unauthenticated flood can't
  spread across users; authenticated non-auth traffic is keyed by user
  (``'user:'+user_id``).

:class:`LimitTier` is a frozen record of a tier's requests-per-minute and burst
allowance; :func:`tier_for` resolves a tier name against a mapping of them. Pure
python, no third-party dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Tier names («имена уровней»).
TIER_AUTH = "auth"
TIER_HEAVY = "heavy"
TIER_LIGHT = "light"

# Path fragment marking authentication endpoints («аутентификация»).
_AUTH_SEGMENT = "/auth/"

# Path suffixes that are always heavy regardless of leading version prefix
# («тяжёлые эндпоинты» — дорогие записи и поиски).
_HEAVY_SUFFIXES: tuple[str, ...] = (
    "/search/hybrid",
    "/graph/query",
    "/gaps/scan",
    "/documents/upload",
    "/ingest/jobs",
)

# Chat message send is heavy: POST to a URL ending in ``/messages`` under chat.
_CHAT_MESSAGES_SUFFIX = "/messages"


@dataclass(frozen=True)
class LimitTier:
    """Immutable rate-limit tier: rpm + burst allowance (§19.4).

    ``name`` — tier label (``'auth'``/``'heavy'``/``'light'``). ``rpm`` — sustained
    requests per minute. ``burst`` — extra tokens allowed above the steady rate for
    short spikes («всплеск»).
    """

    name: str
    rpm: int
    burst: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the tier («словарь для сериализации»)."""
        return {"name": self.name, "rpm": self.rpm, "burst": self.burst}


def _normalize_path(path: str) -> str:
    """Lowercase and strip a trailing slash for stable matching («нормализация»)."""
    normalized = path.rstrip("/")
    return normalized.lower()


def endpoint_tier(method: str, path: str) -> str:
    """Classify a request into ``'auth'`` | ``'heavy'`` | ``'light'`` (§19.4).

    Anything whose path contains ``/auth/`` is ``'auth'`` (any method). A ``POST`` to
    a chat ``…/messages`` URL, or to any of the heavy suffixes (hybrid search, graph
    query, gap scan, document upload, ingest jobs), is ``'heavy'``. Everything else
    is ``'light'`` («всё остальное — лёгкий уровень»).
    """
    normalized = _normalize_path(path)
    if _AUTH_SEGMENT in (normalized + "/"):
        return TIER_AUTH
    if method.upper() == "POST":
        if normalized.endswith(_CHAT_MESSAGES_SUFFIX):
            return TIER_HEAVY
        for suffix in _HEAVY_SUFFIXES:
            if normalized.endswith(suffix):
                return TIER_HEAVY
    return TIER_LIGHT


def rate_limit_key(tier: str, user_id: str | None, ip: str) -> str:
    """Choose the bucket key for a request in *tier* (§19.4).

    Auth traffic and any request without a ``user_id`` is keyed by client IP
    (``'ip:'+ip``) so anonymous floods stay bounded per-source; every other
    authenticated request is keyed by user (``'user:'+user_id``).
    """
    if tier == TIER_AUTH or user_id is None:
        return "ip:" + ip
    return "user:" + user_id


def tier_for(name: str, tiers: Mapping[str, LimitTier]) -> LimitTier:
    """Resolve tier *name* against *tiers*, raising ``KeyError`` if absent (§19.4).

    A thin lookup helper so callers can carry a configured mapping of tiers and
    fetch the concrete :class:`LimitTier` for a name from :func:`endpoint_tier`.
    """
    return tiers[name]
