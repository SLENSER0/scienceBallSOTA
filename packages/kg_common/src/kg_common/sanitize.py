"""Input sanitization & validation for untrusted text (§19.9).

Free-text arriving from users, uploaded documents or tool output is *untrusted*
(«недоверенный ввод»): it may carry ASCII/Unicode control characters, no-break
spaces that break tokenization, oversized payloads, embedded HTML, or explicit
prompt-injection instructions aimed at the LLM. This module normalizes and
validates such text with **pure python** (regex + :mod:`unicodedata`, no
third-party dependency) so it can run everywhere — ingestion, chat API, agent
tools.

Public API:

* :func:`sanitize_text`      — normalize: strip control chars (keep newline/tab),
  collapse NBSP → space, trim, truncate to ``max_len``.
* :func:`detect_injection`   — flag prompt-injection markers (RU/EN).
* :func:`is_safe_identifier` — validate an id/key is ``[A-Za-z0-9_]+``.
* :func:`strip_html`         — remove HTML/XML tags (and script/style blocks).
* :class:`SanitizeResult`    — frozen ``{text, flags, truncated}`` record.
* :func:`sanitize`           — one-shot wrapper returning a :class:`SanitizeResult`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = [
    "DEFAULT_MAX_LEN",
    "SanitizeResult",
    "detect_injection",
    "is_safe_identifier",
    "sanitize",
    "sanitize_text",
    "strip_html",
]

# Default upper bound on sanitized text length — «предел длины» (§19.9).
DEFAULT_MAX_LEN = 8000

# No-break spaces that must collapse to an ordinary space (NBSP, narrow NBSP).
_NBSP_RE = re.compile("[\u00a0\u202f]")

# HTML/XML: <script>/<style> with content, comments, then any remaining tag.
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

# Safe identifier for ids/keys — letters, digits, underscore only («безопасный ключ»).
_IDENT_RE = re.compile(r"[A-Za-z0-9_]+")
_MAX_IDENT_LEN = 256

# Prompt-injection markers (RU/EN). Each (pattern, flag); flag is a canonical label.
_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|preceding)\s+instruction",
            re.IGNORECASE,
        ),
        "ignore_previous_instructions",
    ),
    (
        re.compile(
            r"disregard\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|preceding)",
            re.IGNORECASE,
        ),
        "ignore_previous_instructions",
    ),
    (
        re.compile(
            r"(?:забудь|игнорируй(?:те)?|проигнорируй)\s+"
            r"(?:все\s+)?(?:свои\s+)?(?:предыдущие\s+)?инструкци",
            re.IGNORECASE,
        ),
        "ignore_previous_instructions",
    ),
    (re.compile(r"system\s+prompt", re.IGNORECASE), "system_prompt"),
    (re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?prompt", re.IGNORECASE), "system_prompt"),
    (re.compile(r"системн\w*\s+(?:промпт|подсказк|инструкци)", re.IGNORECASE), "system_prompt"),
)


def _strip_control(s: str) -> str:
    """Drop Unicode control chars (category ``Cc``) except newline/tab (§19.9)."""
    return "".join(c for c in s if c in "\n\t" or unicodedata.category(c) != "Cc")


def _normalize(s: str) -> str:
    """Control-strip, NBSP→space and trim, *without* truncation (§19.9)."""
    text = s.replace("\r\n", "\n").replace("\r", "\n")
    text = _strip_control(text)
    text = _NBSP_RE.sub(" ", text)
    return text.strip()


def sanitize_text(s: str, *, max_len: int = DEFAULT_MAX_LEN) -> str:
    """Normalize untrusted text — «нормализация ввода» (§19.9).

    Steps, in order: convert CR/CRLF to ``\\n``; strip ASCII/Unicode control
    characters (keeping ``\\n`` and ``\\t``); collapse NBSP → ordinary space;
    trim surrounding whitespace; truncate to ``max_len`` characters.
    ``sanitize_text("  a\\x00b\\xa0c  ") == "ab c"``.
    """
    if not s:
        return ""
    text = _normalize(s)
    if 0 <= max_len < len(text):
        text = text[:max_len]
    return text


def detect_injection(s: str) -> list[str]:
    """Return canonical flags for prompt-injection markers found (RU/EN, §19.9).

    Scans case-insensitively for known jailbreak phrases — «попытки обойти
    инструкции» — such as *ignore previous instructions* / *забудь инструкции*
    or requests to reveal the *system prompt* / *системный промпт*. Returns a
    sorted, de-duplicated list of flag labels; empty when the text is clean.
    """
    if not s:
        return []
    found: set[str] = set()
    for pattern, flag in _INJECTION_PATTERNS:
        if pattern.search(s):
            found.add(flag)
    return sorted(found)


def is_safe_identifier(s: str) -> bool:
    """True iff ``s`` is a safe id/key — ``[A-Za-z0-9_]+``, no spaces (§19.9).

    Rejects empty strings, whitespace, punctuation, path/URL separators, non-ASCII
    letters and anything longer than 256 chars. ``is_safe_identifier("run_42")``
    is ``True``; ``"run 42"`` and ``"a-b"`` are ``False``.
    """
    if not s or len(s) > _MAX_IDENT_LEN:
        return False
    return _IDENT_RE.fullmatch(s) is not None


def strip_html(s: str) -> str:
    """Remove HTML/XML tags (and ``<script>``/``<style>`` blocks) — «убрать теги» (§19.9).

    ``<script>``/``<style>`` elements are dropped *with* their contents, HTML
    comments are removed, and every remaining ``<...>`` tag is stripped, leaving
    the surrounding text intact.
    ``strip_html("<p>Hi <b>there</b></p>") == "Hi there"``.
    """
    if not s:
        return ""
    text = _SCRIPT_RE.sub("", s)
    text = _STYLE_RE.sub("", text)
    text = _COMMENT_RE.sub("", text)
    return _TAG_RE.sub("", text)


@dataclass(frozen=True, slots=True)
class SanitizeResult:
    """Immutable outcome of :func:`sanitize` — «результат санитайзинга» (§19.9).

    ``text`` is the normalized string, ``flags`` are prompt-injection markers
    (:func:`detect_injection`), ``truncated`` says whether ``max_len`` clipped
    the input.
    """

    text: str
    flags: tuple[str, ...]
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — ``flags`` as a plain list (§19.9)."""
        return {"text": self.text, "flags": list(self.flags), "truncated": self.truncated}


def sanitize(
    s: str,
    *,
    max_len: int = DEFAULT_MAX_LEN,
    strip_tags: bool = False,
) -> SanitizeResult:
    """Normalize, flag injection and report truncation in one pass (§19.9).

    Optionally strips HTML first (``strip_tags=True``), then normalizes via
    :func:`sanitize_text` and flags prompt-injection markers on the *full*
    normalized text — so a marker is still caught even when truncation would
    clip it. Returns a frozen :class:`SanitizeResult`.
    """
    raw = strip_html(s) if (strip_tags and s) else (s or "")
    normalized = _normalize(raw)
    flags = detect_injection(normalized)
    truncated = 0 <= max_len < len(normalized)
    text = normalized[:max_len] if truncated else normalized
    return SanitizeResult(text=text, flags=tuple(flags), truncated=truncated)
