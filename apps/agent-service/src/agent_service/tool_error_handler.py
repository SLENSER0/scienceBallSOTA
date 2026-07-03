"""§13.16 обработчик ошибок инструментов / tool-error handler (pure python).

When an agent tool call raises, the agent loop needs a *uniform* verdict: what kind
of failure was it, is it worth retrying, and what safe one-liner do we surface to the
LLM/context window? This module turns a raw :class:`Exception` into a frozen
:class:`ToolErrorResult` (§13.6 tools → §13.16 error verdict) so every tool fails the
same way:

* ``tool``      — name of the tool that raised (``"graph_search"`` …).
* ``kind``      — classified failure bucket: ``timeout`` / ``not_found`` /
  ``invalid_args`` / ``unknown`` (класс ошибки / error class).
* ``message``   — short, redacted-safe RU/EN reason for the context window (без
  секретов / no secrets — see :func:`_redact`).
* ``retryable`` — is another attempt worth it? (стоит ли повтор / retry worth it).

:func:`handle_tool_error` builds the verdict; :func:`should_retry` combines the
verdict's ``retryable`` flag with an attempt budget. Nothing here touches the graph
store or an LLM, so the whole module is unit-testable without a seeded Kuzu database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Failure buckets and whether each is worth retrying (класс → повтор / kind → retry).
_RETRYABLE_KINDS = frozenset({"timeout"})

# Substrings (lowercased) that classify an exception by type-name or message text.
_TIMEOUT_HINTS = ("timeout", "timederror", "timed out", "deadline")
_NOT_FOUND_HINTS = ("notfound", "not found", "no such", "missing", "does not exist")
_INVALID_ARGS_HINTS = ("valueerror", "typeerror", "invalid", "bad argument", "keyerror")

# Redaction: collapse anything that looks like a secret/token/path into a placeholder.
_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|pwd)\b\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),  # long opaque blobs / keys
    re.compile(r"(?:/[^\s/]+){2,}"),  # absolute-ish filesystem paths
)
_REDACTED = "[redacted]"
_MAX_MESSAGE = 200  # cap the surfaced reason so it never floods the context window


@dataclass(frozen=True)
class ToolErrorResult:
    """One tool failure's verdict (§13.16).

    Frozen and JSON-serialisable via :meth:`as_dict`. ``tool`` and ``kind`` are always
    set; ``message`` is a redacted-safe one-liner and ``retryable`` says whether the
    agent loop should try again (subject to an attempt budget — see
    :func:`should_retry`).
    """

    tool: str
    kind: str
    message: str
    retryable: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{tool, kind, message, retryable}`` (stable order)."""
        return {
            "tool": self.tool,
            "kind": self.kind,
            "message": self.message,
            "retryable": self.retryable,
        }


def _classify(exc: Exception) -> str:
    """Bucket an exception into ``timeout``/``not_found``/``invalid_args``/``unknown``.

    Looks at both the exception's type name and its message text (lowercased). Timeout
    wins first, then not-found, then invalid-args; anything unrecognised is ``unknown``.
    """
    haystack = f"{type(exc).__name__} {exc}".lower()
    if any(hint in haystack for hint in _TIMEOUT_HINTS):
        return "timeout"
    if any(hint in haystack for hint in _NOT_FOUND_HINTS):
        return "not_found"
    if any(hint in haystack for hint in _INVALID_ARGS_HINTS):
        return "invalid_args"
    return "unknown"


def _redact(text: str) -> str:
    """Strip likely secrets/tokens/paths from ``text`` and cap its length.

    Redaction is best-effort but conservative: ``api_key=…`` pairs, long opaque blobs
    and absolute filesystem paths collapse to ``[redacted]`` (никаких секретов в
    контекст / no secrets into context). The result is trimmed to ``_MAX_MESSAGE``.
    """
    redacted = text
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    redacted = " ".join(redacted.split())  # normalise whitespace/newlines
    if len(redacted) > _MAX_MESSAGE:
        redacted = redacted[:_MAX_MESSAGE].rstrip() + "…"
    return redacted


def handle_tool_error(tool: str, exc: Exception) -> ToolErrorResult:
    """Turn a raised ``exc`` from ``tool`` into a frozen :class:`ToolErrorResult`.

    Classifies the failure (:func:`_classify`), derives ``retryable`` from the kind
    (only ``timeout`` retries), and builds a redacted-safe ``message`` from the
    exception text (:func:`_redact`). A blank exception message falls back to the
    exception type name so ``message`` is never empty.
    """
    kind = _classify(exc)
    raw = str(exc).strip() or type(exc).__name__
    return ToolErrorResult(
        tool=tool,
        kind=kind,
        message=_redact(raw),
        retryable=kind in _RETRYABLE_KINDS,
    )


def should_retry(result: ToolErrorResult, attempt: int, max_attempts: int) -> bool:
    """Decide whether the agent loop should retry after ``result``.

    Retries only when the verdict is ``retryable`` AND we have budget left: ``attempt``
    is 1-based (the attempt that just failed), so the next try is allowed while
    ``attempt < max_attempts``. Non-positive ``max_attempts`` never retries.
    """
    if not result.retryable:
        return False
    if max_attempts <= 0:
        return False
    return attempt < max_attempts
