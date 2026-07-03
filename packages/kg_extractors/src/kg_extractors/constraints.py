"""Multi-parameter numeric constraint parsing (§24.4).

Parses RU/EN free-text requirements into a list of :class:`Constraint` records,
each pairing an (optional) *parameter* name with a numeric *operator* over a
value or a range, plus the raw + canonical unit. It handles the shapes that show
up in mining/metallurgy technical requirements, e.g.::

    «≤1000 мг/дм³»                 -> <= 1000 (mg/L)
    «сульфаты 200–300 мг/л»        -> range 200..300 for parameter "сульфаты"
    «не менее 90%»                 -> >= 90 (percent)
    «плотность тока 250 А/м²»      -> = 250 for parameter "плотность тока"

Pure-python / regex only. Unit tokens and their canonicalization are reused from
:mod:`kg_extractors.units` (single source of truth for the RU/EN unit zoo) so a
parsed unit is normalized with :func:`kg_extractors.units.to_canonical`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from kg_extractors.units import (
    _NUM,
    _OPS,
    _UNIT_BOUNDARY,
    _UNIT_RE,
    to_canonical,
)

# ---------------------------------------------------------------------------
# Constraint record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Constraint:
    """One numeric condition extracted from requirement text (§24.4).

    ``operator`` is one of ``<``, ``<=``, ``>``, ``>=``, ``=`` (single value) or
    ``range`` (``min``/``max`` populated). ``parameter`` is the free-text name the
    constraint applies to (``None`` for a bare/leading constraint). ``source_span``
    is the exact matched substring for provenance / span validation.
    """

    parameter: str | None
    operator: str
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    normalized_value: float | None = None
    normalized_min: float | None = None
    normalized_max: float | None = None
    normalized_unit: str | None = None
    source_span: str = ""

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict, dropping unset (None) numeric fields."""
        out: dict[str, object] = {"parameter": self.parameter, "operator": self.operator}
        for key in (
            "value",
            "min",
            "max",
            "unit",
            "normalized_value",
            "normalized_min",
            "normalized_max",
            "normalized_unit",
        ):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        out["source_span"] = self.source_span
        return out


# ---------------------------------------------------------------------------
# Patterns / vocab
# ---------------------------------------------------------------------------

# RU multi-word / word operators (longest phrases first so alternation is greedy).
_RU_OPS: dict[str, str] = {
    "не более": "<=",
    "не менее": ">=",
    "не выше": "<=",
    "не ниже": ">=",
    "менее": "<",
    "более": ">",
    "от": ">=",
    "до": "<=",
}
# Word tokens that are operators (not part of a parameter name).
_OP_WORDS = {"не", "более", "менее", "выше", "ниже", "от", "до", "по"}

# A parameter name is a trailing run of letter-words (RU/EN) before the number.
_PARAM_TAIL = re.compile(r"([А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z \-]*?)\s*$")

# range: "200–300 мг/л" / "0.1-0.3 м/с" / "от 100 до 300 т/сут". Unit REQUIRED so
# bare hyphenated year pairs ("2015-2020") are not misread as ranges.
_RANGE_RE = re.compile(
    rf"(?:от\s*)?(?P<lo>{_NUM})\s*(?:–|—|-|\.\.|до|to)\s*(?P<hi>{_NUM})"
    rf"\s*(?P<unit>{_UNIT_RE}){_UNIT_BOUNDARY}",
    re.IGNORECASE,
)
# inequality: "≤1000 мг/дм³", "<200 мг/л", "не менее 90%", "от 100 т/сут".
_INEQ_RE = re.compile(
    rf"(?P<op>≤|⩽|≥|⩾|<|>|≈|~|не более|не менее|не выше|не ниже|менее|более|от|до)"
    rf"\s*(?P<val>{_NUM})\s*(?P<unit>{_UNIT_RE})?",
    re.IGNORECASE,
)
# bare "value + unit": "250 А/м²", "0.2 м/с", "95%" (unit REQUIRED + word boundary).
_BARE_RE = re.compile(
    rf"(?P<val>{_NUM})\s*(?P<unit>{_UNIT_RE}){_UNIT_BOUNDARY}",
    re.IGNORECASE,
)


def _to_float(raw: str) -> float:
    """Parse a numeric token, accepting a decimal comma and a leading sign."""
    return float(raw.replace(",", ".").replace("+", ""))


def _param_before(text: str, pos: int) -> str | None:
    """Return the parameter name (letter-word run) ending just before ``pos``."""
    m = _PARAM_TAIL.search(text[:pos])
    if not m:
        return None
    words = m.group(1).split()
    while words and words[0].lower() in _OP_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _OP_WORDS:
        words.pop()
    words = words[-3:]  # keep the closest few words for determinism
    return " ".join(words) or None


def _normalized(value: float | None, unit: str | None) -> tuple[float | None, str | None]:
    if value is None or not unit:
        return None, None
    norm = to_canonical(value, unit)
    return (None, None) if norm is None else (norm.value, norm.unit)


def _make_value(
    parameter: str | None, operator: str, value: float, unit: str | None, span: str
) -> Constraint:
    nv, nu = _normalized(value, unit)
    return Constraint(
        parameter=parameter,
        operator=operator,
        value=value,
        unit=unit,
        normalized_value=nv,
        normalized_unit=nu,
        source_span=span.strip(),
    )


def _make_range(
    parameter: str | None, lo: float, hi: float, unit: str | None, span: str
) -> Constraint:
    lo, hi = min(lo, hi), max(lo, hi)
    nlo, nu = _normalized(lo, unit)
    nhi, _ = _normalized(hi, unit)
    return Constraint(
        parameter=parameter,
        operator="range",
        min=lo,
        max=hi,
        unit=unit,
        normalized_min=nlo,
        normalized_max=nhi,
        normalized_unit=nu,
        source_span=span.strip(),
    )


def parse_constraints(text: str) -> list[Constraint]:
    """Extract every numeric constraint from ``text`` (§24.4).

    Ranges are matched first, then inequalities, then bare value+unit pairs;
    already-consumed character spans are never re-parsed, so a single number is
    reported once under its most specific operator.
    """
    if not text:
        return []
    t = unicodedata.normalize("NFKC", text)
    out: list[Constraint] = []
    covered: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in covered)

    for m in _RANGE_RE.finditer(t):
        covered.append(m.span())
        out.append(
            _make_range(
                _param_before(t, m.start()),
                _to_float(m.group("lo")),
                _to_float(m.group("hi")),
                m.group("unit"),
                m.group(0),
            )
        )

    for m in _INEQ_RE.finditer(t):
        if overlaps(*m.span()):
            continue
        raw_op = m.group("op").lower()
        op = _OPS.get(raw_op) or _RU_OPS.get(raw_op)
        if not op or op == "approx":
            continue
        covered.append(m.span())
        out.append(
            _make_value(
                _param_before(t, m.start()),
                op,
                _to_float(m.group("val")),
                m.group("unit"),
                m.group(0),
            )
        )

    for m in _BARE_RE.finditer(t):
        if overlaps(*m.span()):
            continue
        covered.append(m.span())
        out.append(
            _make_value(
                _param_before(t, m.start()),
                "=",
                _to_float(m.group("val")),
                m.group("unit"),
                m.group(0),
            )
        )

    out.sort(key=lambda c: t.find(c.source_span))
    return out
