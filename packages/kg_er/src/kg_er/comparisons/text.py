"""Text cleaning + feature engineering for ER (§8.3).

Deterministic, dependency-light normalization used to build Splink feature
columns. Kept pure (no I/O) so it is trivially testable and reused across the
per-type feature builders in :mod:`kg_er.pipeline`.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s\-]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_INITIALS_RE = re.compile(r"\b([а-яёa-z])[а-яёa-z]*\.?", re.IGNORECASE)


def clean_text(value: str | None) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace."""
    if not value:
        return ""
    # NFKD fold so "Å"/"ё" style chars normalize deterministically.
    norm = unicodedata.normalize("NFKD", str(value))
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.lower().replace("ё", "е")
    norm = _PUNCT_RE.sub(" ", norm)
    return _WS_RE.sub(" ", norm).strip()


def token_set(value: str | None) -> frozenset[str]:
    """Cleaned token set (for Jaccard-style comparisons)."""
    return frozenset(t for t in clean_text(value).split() if t)


def jaccard(a: str | None, b: str | None) -> float:
    """Token-set Jaccard similarity in [0, 1]."""
    sa, sb = token_set(a), token_set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def split_person_name(full: str | None) -> tuple[str, str, str]:
    """Return (given_name, family_name, initials) from a person name.

    Handles both "Ivanov I.I." and "Ivan Ivanov" orderings heuristically:
    a token that is all-initials/short is treated as given/initials.
    """
    cleaned = clean_text(full)
    if not cleaned:
        return "", "", ""
    parts = cleaned.split()
    initials = "".join(p[0] for p in parts if p)
    if len(parts) == 1:
        return "", parts[0], initials
    # Longest token is most likely the family name in RU/EN mixed data.
    family = max(parts, key=len)
    given = " ".join(p for p in parts if p != family) or ""
    return given, family, initials


def email_domain(email: str | None) -> str:
    if not email or "@" not in str(email):
        return ""
    return str(email).rsplit("@", 1)[-1].strip().lower()


def designation_code(value: str | None) -> str:
    """Extract an alloy/standard designation code (AA/UNS/EN/GOST style).

    e.g. "Alloy AA6061-T6" -> "aa6061"; "12Х18Н10Т" -> "12х18н10т".
    """
    cleaned = clean_text(value)
    m = re.search(r"\b([a-z]{0,3}\s?\d[\w\-]*)\b", cleaned)
    if not m:
        return ""
    return _WS_RE.sub("", m.group(1))
