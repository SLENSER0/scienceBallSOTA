"""§7.4 numeric value parser — single value / range / inequality tokens (RU & EN).

Parses one measurement token (as found in a table cell or an extracted span) into a
frozen :class:`ParsedValue`: a magnitude (or a min/max range), a comparison operator
(``eq`` / ``lt`` / ``lte`` / ``gt`` / ``gte`` / ``range`` / ``approx``), an optional
raw unit, and an optional ``±`` uncertainty. It handles the shapes seen in
mining/metallurgy data::

    «148 HV»            -> eq 148            (unit HV)
    «≤ 1000 мг/дм³»     -> lte 1000          (unit мг/дм³)
    «200–300 МПа»       -> range 200..300    (unit МПа)
    «≈ 5.0»             -> approx 5.0
    «5.0 ± 0.2 %»       -> eq 5.0 ± 0.2      (unit %)
    «10^3 А/м²» / «1e3» -> 1000              (scientific)
    «2,5»               -> 2.5               (decimal comma)

Pure-python / regex only. The numeric-token regex (:data:`kg_extractors.units._NUM`)
and the operator-symbol map (:data:`kg_extractors.units._OPS`) are reused from
:mod:`kg_extractors.units` — the single source of truth for the RU/EN unit zoo.

Values and units are kept **raw** so asserted magnitudes are preserved: unit
canonicalization via :func:`kg_extractors.units.to_canonical` is deliberately left to
downstream consumers, since converting «200 МПа» to bar would rewrite the parsed
magnitude that this token-level parser is expected to report verbatim.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from kg_extractors.units import _NUM, _OPS

# ---------------------------------------------------------------------------
# Parsed value record (§7.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedValue:
    """One numeric value parsed from a measurement token (§7.4).

    ``operator`` is one of ``eq`` / ``lt`` / ``lte`` / ``gt`` / ``gte`` / ``approx``
    (single ``value``) or ``range`` (``value_min`` / ``value_max`` populated).
    ``unit`` is the raw trailing unit token (``None`` if absent), ``uncertainty`` the
    ``±`` half-width (``None`` if absent), and ``source`` the original raw string for
    provenance / span validation.
    """

    value: float | None = None
    value_min: float | None = None
    value_max: float | None = None
    operator: str = "eq"
    unit: str | None = None
    uncertainty: float | None = None
    source: str = ""

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict, dropping unset (None) optional fields."""
        out: dict[str, object] = {"operator": self.operator}
        for key in ("value", "value_min", "value_max", "unit", "uncertainty"):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        out["source"] = self.source
        return out


# ---------------------------------------------------------------------------
# Operator vocabulary
# ---------------------------------------------------------------------------

# Map units._OPS signs (and their ASCII spellings) to §7.4 operator names.
_SIGN_TO_NAME: dict[str, str] = {
    "<=": "lte",
    ">=": "gte",
    "<": "lt",
    ">": "gt",
    "approx": "approx",
}
_ASCII_SIGNS: dict[str, str] = {"<=": "<=", ">=": ">="}
# RU word / phrase operators (longest phrases first so alternation is greedy).
_RU_OP_TO_NAME: dict[str, str] = {
    "не более": "lte",
    "не менее": "gte",
    "не выше": "lte",
    "не ниже": "gte",
    "менее": "lt",
    "более": "gt",
}


def _operator_name(token: str) -> str | None:
    """Map an operator token (symbol or RU word) to a §7.4 operator name."""
    ru = _RU_OP_TO_NAME.get(token)
    if ru:
        return ru
    sign = _OPS.get(token) or _ASCII_SIGNS.get(token)
    return _SIGN_TO_NAME.get(sign) if sign else None


# ---------------------------------------------------------------------------
# Numeric-token patterns
# ---------------------------------------------------------------------------

# A numeric token, extending units._NUM with scientific forms «1e3» and «10^3».
_CARET = r"\d+(?:[.,]\d+)?\s*\^\s*[-+]?\d+"
_VALTOK = rf"(?:{_CARET}|{_NUM}(?:[eE][-+]?\d+)?)"

_UNIT = r"(?P<unit>.*?)"
_UNC = rf"(?:\s*(?:±|\+/-|\+-)\s*(?P<unc>{_VALTOK}))?"

# range: «200–300 МПа», «0.1-0.3 м/с», «от 100 до 300 т/сут».
_RANGE_RE = re.compile(
    rf"^\s*(?:от\s+)?(?P<lo>{_VALTOK})\s*(?:–|—|\.\.|-|до|to)\s*(?P<hi>{_VALTOK})"
    rf"\s*{_UNIT}\s*$",
    re.IGNORECASE,
)
# inequality / approx: «≤ 1000 мг/дм³», «≈ 5.0», «не более 90 %».
_OP_ALT = r"не более|не менее|не выше|не ниже|менее|более|≤|⩽|≥|⩾|<=|>=|<|>|≈|~"
_OPVAL_RE = re.compile(
    rf"^\s*(?P<op>{_OP_ALT})\s*(?P<val>{_VALTOK}){_UNC}\s*{_UNIT}\s*$",
    re.IGNORECASE,
)
# bare value (+ optional ± uncertainty): «148 HV», «5.0 ± 0.2 %», «2,5».
_BARE_RE = re.compile(
    rf"^\s*(?P<val>{_VALTOK}){_UNC}\s*{_UNIT}\s*$",
    re.IGNORECASE,
)


def _to_float(token: str) -> float:
    """Parse a numeric token: decimal comma, scientific «1e3» and caret «10^3»."""
    s = token.strip().replace(" ", "")
    if "^" in s:
        base, _, exp = s.partition("^")
        return float(base.replace(",", ".")) ** float(exp.replace(",", "."))
    return float(s.replace(",", "."))


def _clean_unit(raw: str | None) -> str | None:
    """Trim whitespace and stray trailing punctuation; empty -> None."""
    if not raw:
        return None
    unit = raw.strip(" \t.,;")
    return unit or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_value(raw: str) -> ParsedValue | None:
    """Parse one value token into a :class:`ParsedValue`, or ``None`` if no number.

    Tries a range first (``200–300``), then an operator/approx form (``≤ 1000``,
    ``≈ 5.0``), then a bare value with an optional ``±`` uncertainty (``5.0 ± 0.2``).
    A token whose leading character is not a number (junk, empty) returns ``None``.
    """
    if not raw or not raw.strip():
        return None
    text = unicodedata.normalize("NFKC", raw).strip()

    m = _RANGE_RE.match(text)
    if m:
        lo, hi = _to_float(m.group("lo")), _to_float(m.group("hi"))
        return ParsedValue(
            value_min=min(lo, hi),
            value_max=max(lo, hi),
            operator="range",
            unit=_clean_unit(m.group("unit")),
            source=raw,
        )

    m = _OPVAL_RE.match(text)
    if m:
        op = _operator_name(m.group("op").lower())
        if op:
            unc = m.group("unc")
            return ParsedValue(
                value=_to_float(m.group("val")),
                operator=op,
                unit=_clean_unit(m.group("unit")),
                uncertainty=_to_float(unc) if unc else None,
                source=raw,
            )

    m = _BARE_RE.match(text)
    if m:
        unc = m.group("unc")
        return ParsedValue(
            value=_to_float(m.group("val")),
            operator="eq",
            unit=_clean_unit(m.group("unit")),
            uncertainty=_to_float(unc) if unc else None,
            source=raw,
        )

    return None
