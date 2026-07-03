"""Authorization-header and SSE stream-token parsing/classification (§19.2 auth).

HTTP clients present credentials in the ``Authorization`` header, while browser
``EventSource`` clients — which cannot set custom headers — fall back to a
``?token=`` query parameter. This module gives the auth layer a single, log-safe
way to *parse* the header into its scheme and credential and to *classify* the
credential («классификация учётных данных») without trusting it:

* ``sk_`` prefixed opaque secrets are API keys («ключ API»);
* three dot-separated base64url segments (``header.payload.sig``) are JWTs;
* everything else is ``unknown`` and must be rejected by the caller.

Parsing never validates a signature or an expiry — it only shapes the input so
downstream verifiers (:mod:`kg_common.security.jwt_keyset`,
:mod:`kg_common.security.api_key`) can dispatch. A parsed :class:`AuthToken`
carries the raw credential, so treat :meth:`AuthToken.as_dict` output as secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

_BEARER = "Bearer"
_API_KEY_PREFIX = "sk_"
_JWT_SEGMENTS = 3
_STREAM_QUERY_KEY = "token"

# base64url alphabet per RFC 4648 §5 (no padding on the wire for JWT segments).
_B64URL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

_KIND_JWT = "jwt"
_KIND_API_KEY = "api_key"
_KIND_STREAM = "stream"
_KIND_UNKNOWN = "unknown"


@dataclass(frozen=True)
class AuthToken:
    """Immutable, parsed view of a presented credential («учётные данные»).

    :param scheme: the normalized auth scheme, e.g. ``"Bearer"`` or ``"Basic"``.
    :param kind: credential class, one of ``jwt``/``api_key``/``stream``/``unknown``.
    :param credential: the raw credential exactly as presented; treat as secret.
    """

    scheme: str
    kind: str
    credential: str

    def as_dict(self) -> dict[str, object]:
        """Return a serializable view; the ``credential`` field is secret."""
        return asdict(self)


def _is_base64url(segment: str) -> bool:
    """Return whether *segment* is a non-empty base64url token (RFC 4648 §5)."""
    return bool(segment) and all(ch in _B64URL_CHARS for ch in segment)


def classify_credential(cred: str) -> str:
    """Classify a bare credential string into its kind (§19.2).

    Rules, in order: an ``sk_`` prefix marks an API key; three non-empty
    dot-separated base64url segments mark a JWT; anything else is ``unknown``.
    This inspects shape only — it never verifies a signature or an expiry.
    """
    if cred.startswith(_API_KEY_PREFIX):
        return _KIND_API_KEY
    segments = cred.split(".")
    if len(segments) == _JWT_SEGMENTS and all(_is_base64url(s) for s in segments):
        return _KIND_JWT
    return _KIND_UNKNOWN


def parse_authorization(header: str | None) -> AuthToken | None:
    """Parse an ``Authorization`` header into an :class:`AuthToken` (§19.2).

    Returns ``None`` when *header* is missing/blank or carries no credential
    (e.g. a lone ``"Bearer"``). The scheme is normalized to its canonical
    capitalized form (``bearer`` → ``Bearer``); the credential keeps its exact
    casing. For non-``Bearer`` schemes the kind is always ``unknown`` — only a
    Bearer credential is classified via :func:`classify_credential`.
    """
    if header is None:
        return None
    stripped = header.strip()
    if not stripped:
        return None
    parts = stripped.split(None, 1)
    if len(parts) != 2:
        return None
    raw_scheme, credential = parts[0], parts[1].strip()
    if not credential:
        return None
    scheme = raw_scheme.capitalize()
    kind = classify_credential(credential) if scheme == _BEARER else _KIND_UNKNOWN
    return AuthToken(scheme=scheme, kind=kind, credential=credential)


def stream_token_from_query(qs: Mapping[str, str]) -> str | None:
    """Return the SSE ``?token=`` value from a query mapping, or ``None`` (§19.2).

    Browser ``EventSource`` clients cannot set an ``Authorization`` header, so
    the single-use stream token («потоковый токен») rides on the query string. A
    missing or empty ``token`` key yields ``None``.
    """
    value = qs.get(_STREAM_QUERY_KEY)
    if not value:
        return None
    return value
