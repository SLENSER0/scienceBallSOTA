"""Secret/PII redaction for logs and errors (§19.7 secrets management).

No secret or PII must leak into structured logs, error payloads or telemetry
(«секреты и персональные данные не должны попадать в логи»). :func:`redact`
masks free text — API keys / bearer tokens, ``sk-…`` OpenAI/OpenRouter keys,
long hex/base64 blobs, emails (keeping only the domain), JWTs (three base64
segments) and connection-string passwords (``postgres://user:PASS@``).
:func:`redact_mapping` walks a dict/list structure, fully masking values under
known-sensitive keys (password / token / api_key / secret / authorization /
jwt_secret) and running :func:`redact` over every remaining string. Both return
**new** objects and never mutate the input («возвращаем копию, не мутируем»).
Pure-python, regex only — no third-party dependency.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Redaction marker («маска») substituted for a secret.
_MASK = "***"

# Substrings that mark a mapping key as secret-bearing (matched case-insensitively).
_SENSITIVE_KEY_MARKERS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "token",
        "api_key",
        "apikey",
        "secret",
        "authorization",
        "jwt",
        "access_token",
        "refresh_token",
        "private_key",
    }
)

# JSON Web Token: header ``eyJ…`` + two more base64url segments.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

# Connection-string password: ``scheme://user:PASSWORD@host``.
_CONN_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://[^:/@\s]+:)([^@\s/]+)(@)")

# ``Authorization: Bearer <token>`` (also a bare ``Bearer <token>``).
_BEARER_RE = re.compile(r"\b(bearer\s+)([A-Za-z0-9._~+/=-]{8,})", re.IGNORECASE)

# OpenAI / OpenRouter style API key: ``sk-…`` (incl. ``sk-or-v1-…``).
_APIKEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")

# Email — keep the domain, mask the local part.
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")

# Long opaque secrets: hex (>=32) or base64 (>=40) blobs.
_HEX_RE = re.compile(r"\b[A-Fa-f0-9]{32,}\b")
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}")


def _stub(secret: str, keep: int = 4) -> str:
    """Mask *secret* keeping only its last *keep* chars, or a bare mask if short."""
    s = secret.strip()
    if len(s) <= keep + 4:
        return _MASK
    return f"{_MASK}{s[-keep:]}"


def _is_sensitive_key(key: object) -> bool:
    """True if *key* names a secret-bearing field («чувствительный ключ»)."""
    k = str(key).lower()
    return any(marker in k for marker in _SENSITIVE_KEY_MARKERS)


def _repl_conn(m: re.Match[str]) -> str:
    return f"{m.group(1)}{_MASK}{m.group(3)}"


def _repl_bearer(m: re.Match[str]) -> str:
    return f"{m.group(1)}{_stub(m.group(2))}"


def _repl_apikey(m: re.Match[str]) -> str:
    return f"sk-{_stub(m.group(0)[3:])}"


def _repl_email(m: re.Match[str]) -> str:
    return f"{_MASK}@{m.group(2)}"


def _repl_stub(m: re.Match[str]) -> str:
    return _stub(m.group(0))


def redact(text: str) -> str:
    """Return *text* with secrets and PII masked (§19.7).

    Rules are applied most-specific first (JWT → connection string → bearer →
    ``sk-`` key → email → hex/base64 blob) so every token is masked exactly once.
    """
    out = _JWT_RE.sub("[REDACTED_JWT]", text)
    out = _CONN_RE.sub(_repl_conn, out)
    out = _BEARER_RE.sub(_repl_bearer, out)
    out = _APIKEY_RE.sub(_repl_apikey, out)
    out = _EMAIL_RE.sub(_repl_email, out)
    out = _HEX_RE.sub(_repl_stub, out)
    out = _B64_RE.sub(_repl_stub, out)
    return out


def redact_mapping(value: Any) -> Any:
    """Recursively redact *value*, returning a **new** structure (§19.7).

    A dict value under a sensitive key (:data:`_SENSITIVE_KEY_MARKERS`) is fully
    masked; every other string is passed through :func:`redact`. Lists/tuples are
    walked element-wise; scalars (int/float/bool/None) pass through unchanged. The
    input is never mutated («вход не мутируется»).
    """
    if isinstance(value, Mapping):
        return {k: (_MASK if _is_sensitive_key(k) else redact_mapping(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_mapping(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_mapping(v) for v in value)
    if isinstance(value, str):
        return redact(value)
    return value
