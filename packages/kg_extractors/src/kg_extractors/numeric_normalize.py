"""§6.20 numeric literal normalization — free-text number surfaces to ``float`` (RU & EN).

Нормализация числовых литералов из свободного текста к :class:`float`.

Pure-python / regex + :mod:`unicodedata` only — no third-party dependency. Folds the
numeric shapes seen in RU/EN mining & metallurgy data into a single machine float:

    «2,5»            -> 2.5        (decimal comma)
    «1e3» / «10^3»   -> 1000.0     (scientific: e-notation and «base^exp» caret)
    «1 000» / NBSP   -> 1000.0     (thousands: ASCII space, NBSP, narrow NBSP, thin)
    «1,000»          -> 1000.0     (comma-grouped thousands, disambiguated from «2,5»)
    «1 000,5»        -> 1000.5     (mixed grouping + decimal, last separator wins)
    «½» / «2½»       -> 0.5 / 2.5  (vulgar unicode fractions, plain and mixed)
    «10-20»          -> 15.0       (range -> arithmetic midpoint)
    «-5» / «−5»      -> -5.0       (ASCII and unicode-minus sign)
    «нет данных»     -> None       (junk / no number)

The comma is context-sensitive: a **decimal** separator in «2,5» but a **thousands**
separator in «1,000». Disambiguation keys on grouping shape — a comma followed by an
exact run of three digits (``\\d{1,3}(,\\d{3})+``) is a group separator; otherwise a
single comma is the decimal mark. Vulgar fractions must be handled *before* NFKC (which
folds «½» to the un-parseable «1⁄2»); everything else is NFKC-folded so superscript and
no-break-space codepoints collapse to their ASCII forms.

Public API:

- :func:`normalize_number` — surface -> ``float`` (or ``None`` when no number is present).
- :func:`parse_percent` — percent surface («50%») -> fraction (``0.5``), or ``None``.
- :func:`describe_number` — surface -> frozen :class:`NumberParse` (value + parse ``kind``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = ["NumberParse", "describe_number", "normalize_number", "parse_percent"]

# Whitespace codepoints used as thousands group separators (ASCII, NBSP, narrow, thin).
_WS_RE = re.compile(r"[\s   ]")
# Unicode minus sign U+2212 — not folded by NFKC, normalized to ASCII "-" for float().
_UNICODE_MINUS = "−"
# A comma-grouped thousands surface: «1,000», «12,345,678» (but never «2,5» -> decimal).
_THOUSANDS_COMMA_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+")

# A single numeric operand inside a range: digits with optional grouping/decimal marks
# (spaces, NBSP, commas, periods). Excludes e-notation/caret so the range dash cannot be
# confused with a sign or exponent; range operands are re-parsed by :func:`_parse_single`.
_NUM_CORE = r"\d[\d.,    ]*\d|\d"
# Range: «10-20», «200–300», «10 .. 20», «от 100 до 300», «10 to 20» -> midpoint.
_RANGE_RE = re.compile(
    r"^\s*(?:от\s+)?"
    r"(?P<lo>[-+]?(?:" + _NUM_CORE + r"))"
    r"\s*(?:\.\.|…|—|–|―|‒|−|-|\bto\b|\bдо\b)\s*"
    r"(?P<hi>[-+]?(?:" + _NUM_CORE + r"))"
    r"\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NumberParse:
    """A numeric surface normalized to a ``float`` with its parse provenance (§6.20).

    ``value`` — the normalized magnitude; ``kind`` — how it was read: ``plain`` /
    ``decimal_comma`` / ``thousands`` / ``scientific`` / ``fraction`` / ``range``;
    ``source`` — the original raw surface, kept verbatim for provenance.
    """

    value: float
    kind: str
    source: str

    def as_dict(self) -> dict[str, object]:
        """Serialize to ``{value, kind, source}``."""
        return {"value": self.value, "kind": self.kind, "source": self.source}


def _vulgar_value(ch: str) -> float | None:
    """Numeric value of a *vulgar fraction* char («½» -> ``0.5``); ``None`` otherwise.

    A plain decimal digit («5») is rejected — only non-decimal numeric codepoints
    (the Unicode vulgar fractions) qualify.
    """
    if unicodedata.decimal(ch, None) is not None:
        return None
    return unicodedata.numeric(ch, None)


def _try_fraction(text: str) -> float | None:
    """Parse a vulgar fraction, plain «½» or mixed «2½» / «2 ½» / «-2½»; else ``None``.

    Handled before NFKC because NFKC folds «½» to the un-parseable «1⁄2».
    """
    body = text.strip()
    sign = 1.0
    if body[:1] in "+-":
        sign = -1.0 if body[0] == "-" else 1.0
        body = body[1:].strip()
    if not body:
        return None
    frac = _vulgar_value(body[-1])
    if frac is None:
        return None
    whole_str = body[:-1].strip()
    if whole_str == "":
        whole = 0.0
    elif whole_str.isdigit():
        whole = float(whole_str)
    else:
        return None
    return sign * (whole + frac)


def _resolve_separators(s: str) -> tuple[str | None, str]:
    """Resolve comma/period grouping vs decimal marks to a float-parseable ``str``.

    Returns ``(resolved, kind)`` where ``kind`` is ``plain`` / ``decimal_comma`` /
    ``thousands``. Assumes grouping whitespace has already been stripped.
    """
    has_comma = "," in s
    has_period = "." in s
    if has_comma and has_period:
        # Both present: the *last-occurring* separator is the decimal mark.
        if s.rfind(",") > s.rfind("."):
            return s.replace(".", "").replace(",", "."), "decimal_comma"
        return s.replace(",", ""), "thousands"
    if has_comma:
        if _THOUSANDS_COMMA_RE.fullmatch(s):
            return s.replace(",", ""), "thousands"
        if s.count(",") == 1:
            return s.replace(",", "."), "decimal_comma"
        return s.replace(",", ""), "thousands"
    if has_period and s.count(".") > 1:
        # Multiple periods can only be period-grouped thousands («1.000.000»).
        return s.replace(".", ""), "thousands"
    return s, "plain"


def _resolve_and_float(s: str) -> float | None:
    """Resolve separators then parse to ``float``; ``None`` on non-numeric input."""
    resolved, _ = _resolve_separators(s.strip())
    if not resolved:
        return None
    try:
        return float(resolved)
    except (ValueError, OverflowError):
        return None


def _parse_caret(s: str) -> float | None:
    """Evaluate a caret power «base^exp» -> ``base ** exp`` («10^3» -> ``1000``)."""
    base_s, _, exp_s = s.partition("^")
    base = _resolve_and_float(base_s)
    exp = _resolve_and_float(exp_s)
    if base is None or exp is None:
        return None
    try:
        return float(base) ** float(exp)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def _parse_single(text: str) -> tuple[float, str] | None:
    """Parse a single (non-range) numeric surface to ``(value, kind)`` or ``None``."""
    s = text.strip()
    if not s:
        return None

    frac = _try_fraction(s)
    if frac is not None:
        return frac, "fraction"

    norm = unicodedata.normalize("NFKC", s).replace(_UNICODE_MINUS, "-")
    despaced = _WS_RE.sub("", norm)
    if not despaced:
        return None
    had_ws = despaced != norm

    if "^" in despaced:
        val = _parse_caret(despaced)
        return (val, "scientific") if val is not None else None

    resolved, kind = _resolve_separators(despaced)
    if resolved is None:
        return None
    try:
        value = float(resolved)
    except (ValueError, OverflowError):
        return None

    if "e" in resolved or "E" in resolved:
        kind = "scientific"
    elif had_ws and kind == "plain":
        kind = "thousands"
    return value, kind


def _try_range(text: str) -> float | None:
    """Parse a numeric range to its arithmetic midpoint («10-20» -> ``15``); else ``None``."""
    m = _RANGE_RE.match(text.strip())
    if not m:
        return None
    lo = _parse_single(m.group("lo"))
    hi = _parse_single(m.group("hi"))
    if lo is None or hi is None:
        return None
    return (lo[0] + hi[0]) / 2.0


def _parse(raw: str) -> tuple[float, str] | None:
    """Core: normalize a raw surface to ``(value, kind)`` or ``None`` (§6.20)."""
    if raw is None:
        return None
    text = str(raw)
    if not text.strip():
        return None
    midpoint = _try_range(text)
    if midpoint is not None:
        return midpoint, "range"
    return _parse_single(text)


def normalize_number(raw: str) -> float | None:
    """Normalize a free-text number surface to a ``float``, or ``None`` (§6.20).

    Handles decimal comma, e-notation/caret scientific, whitespace/comma thousands
    grouping, vulgar unicode fractions and ranges (-> midpoint); junk -> ``None``.
    """
    result = _parse(raw)
    return result[0] if result is not None else None


def describe_number(raw: str) -> NumberParse | None:
    """Normalize *raw* and report both value and parse ``kind``, or ``None`` (§6.20)."""
    result = _parse(raw)
    if result is None:
        return None
    value, kind = result
    return NumberParse(value=value, kind=kind, source=str(raw))


def parse_percent(raw: str) -> float | None:
    """Parse a percent surface («50%») to its fraction (``0.5``), or ``None`` (§6.20).

    Разбор процентной величины к доле единицы. The ``%`` sign is stripped and the
    remaining number is normalized via :func:`normalize_number` then divided by 100;
    a bare number («50») is likewise read as a percentage. Junk -> ``None``.
    """
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", str(raw)).replace("%", "").strip()
    if not text:
        return None
    value = normalize_number(text)
    return value / 100.0 if value is not None else None
