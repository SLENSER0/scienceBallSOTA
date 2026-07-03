"""Secret detection in free text & config (§19.10).

Untrusted text, uploaded config files and tool output may embed live
credentials («секреты в тексте»): OpenAI-style ``sk-…`` keys, AWS ``AKIA…``
access-key ids, JSON Web Tokens, ``Bearer`` tokens, PEM private-key blocks,
long opaque hex/base64 tokens and ``password=…`` assignments. This module
*locates* every such secret with **pure python** (regex only, no third-party
dependency) so callers can block, redact or audit untrusted input.

Public API:

* :class:`SecretHit`  — frozen ``{kind, span, redacted}`` record with
  :meth:`~SecretHit.as_dict`; ``span`` points at the *exact* secret substring.
* :func:`scan_secrets` — positionally-sorted, non-overlapping list of hits.
* :func:`redact`       — mask every detected secret in the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "SecretHit",
    "redact",
    "scan_secrets",
]

# PEM private-key block: header alone, or the whole ``BEGIN…END`` body.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r"(?:[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----)?"
)

# JSON Web Token: header ``eyJ…`` + two more base64url segments.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

# AWS access-key id: ``AKIA``/``ASIA`` prefix + 16 upper-case alnum chars.
_AWS_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")

# OpenAI / OpenRouter style API key: ``sk-…`` (incl. ``sk-or-v1-…``).
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")

# ``Bearer <token>`` — the secret is the token (group 1), not the keyword.
_BEARER_RE = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{16,})")

# ``password=…`` / ``passwd: …`` — the secret is the value (group 1).
_PASSWORD_RE = re.compile(r"""(?i)\b(?:password|passwd|pwd)\s*[:=]\s*"?([^\s"';,]+)""")

# Long opaque tokens: hex (>=32) or base64 (>=40) blobs.
_HEX_RE = re.compile(r"\b[A-Fa-f0-9]{32,}\b")
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}")

# Detection rules, **most-specific first** — on overlap the earlier rule wins.
# Each entry is ``(kind, pattern, group)`` where ``group`` selects the exact
# secret substring (``0`` = whole match).
_PATTERNS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("private_key", _PRIVATE_KEY_RE, 0),
    ("jwt", _JWT_RE, 0),
    ("aws_access_key", _AWS_RE, 0),
    ("api_key", _SK_RE, 0),
    ("bearer", _BEARER_RE, 1),
    ("password_assignment", _PASSWORD_RE, 1),
    ("hex_token", _HEX_RE, 0),
    ("base64_token", _B64_RE, 0),
)


def _placeholder(kind: str) -> str:
    """Length-free, leak-free mask for a *kind* — «маска без утечки» (§19.10)."""
    return f"[REDACTED_{kind.upper()}]"


@dataclass(frozen=True, slots=True)
class SecretHit:
    """One detected secret — «найденный секрет» (§19.10).

    ``kind`` is the canonical detector label (``api_key``/``jwt``/…), ``span`` is
    the ``(start, end)`` half-open offset of the secret in the scanned text so
    ``text[start:end]`` is exactly the secret, and ``redacted`` is a leak-free
    placeholder safe to display or log.
    """

    kind: str
    span: tuple[int, int]
    redacted: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — ``span`` as a plain ``[start, end]`` list (§19.10)."""
        return {"kind": self.kind, "span": list(self.span), "redacted": self.redacted}


def scan_secrets(text: str) -> list[SecretHit]:
    """Locate every secret in *text* — «поиск секретов» (§19.10).

    Runs each detector (private key → JWT → AWS ``AKIA`` → ``sk-`` key → bearer →
    ``password=`` → hex/base64 blob) and resolves overlaps in favour of the
    most-specific rule, so a ``sk-…`` key is never also reported as a base64
    blob. Returns hits sorted by start offset; the list is empty for clean text.
    """
    if not text:
        return []
    raw: list[tuple[int, int, str]] = []
    for kind, pattern, group in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(group)
            if start < end:  # skip empty captures
                raw.append((start, end, kind))
    accepted: list[tuple[int, int, str]] = []
    for start, end, kind in raw:  # raw is in most-specific-first order
        if any(start < e and s < end for s, e, _ in accepted):
            continue
        accepted.append((start, end, kind))
    accepted.sort(key=lambda hit: hit[0])
    return [
        SecretHit(kind=kind, span=(start, end), redacted=_placeholder(kind))
        for start, end, kind in accepted
    ]


def redact(text: str) -> str:
    """Return *text* with every detected secret replaced by its mask (§19.10).

    Uses :func:`scan_secrets` and rewrites each secret span with its leak-free
    :attr:`SecretHit.redacted` placeholder; surrounding text (including the
    ``password=`` key or ``Bearer`` keyword) is left intact. Clean text is
    returned unchanged.
    """
    hits = scan_secrets(text)
    if not hits:
        return text
    parts: list[str] = []
    cursor = 0
    for hit in hits:
        start, end = hit.span
        parts.append(text[cursor:start])
        parts.append(hit.redacted)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)
