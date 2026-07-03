"""Standard alloy-grade + composition-fraction parsing (§6.4).

Распознаёт стандартные марки сплавов и типы долей (масс.%/ат.%).

Two deterministic, dependency-light parsers (regex only):

- :func:`parse_grade` — recognizes standard alloy designations with an optional
  temper: Aluminum-Association (``AA2024`` / ``2024-T6`` / ``6061-T651``), AISI
  stainless (``316L``), Inconel nickel superalloys (``Inconel 718``) and
  titanium alloys (``Ti-6Al-4V``). Returns the single leftmost
  :class:`GradeMatch`, or ``None`` when no grade is present.
- :func:`parse_composition_fractions` — extracts ``<element> <value>
  <fraction>`` mentions, distinguishing weight-percent (``wt%`` / ``масс.%``)
  from atomic-percent (``at.%`` / ``ат.%``) and flagging ``balance`` / ``bal.``
  / ``ост.`` remainders (``is_balance=True``, ``value=None``).

Element symbols are validated against the periodic-table set defined in
:mod:`kg_extractors.composition_extractor` (reused here, never redefined).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from kg_extractors.composition_extractor import _ELEMENTS, _RU_ELEMENT

# ---------------------------------------------------------------------------
# Standard alloy-grade recognition
# ---------------------------------------------------------------------------
# Temper suffixes: T-tempers (T6, T651, T6511), H-tempers (H14), and the bare
# annealed/as-fabricated/solution letters O / F / W.
_TEMPER = r"T\d{1,4}|H\d{1,3}|O|F|W"

# Aluminum-Association designation with an explicit "AA" prefix; temper optional.
_AA_PREFIX_RE = re.compile(
    rf"\bAA[\s-]?([1-8]\d{{3}})(?:[\s-]?({_TEMPER}))?\b",
    re.IGNORECASE,
)
# 4-digit designation that carries a temper (no prefix needed). The temper is
# REQUIRED so a bare 4-digit year is never mistaken for an alloy grade.
_AL_TEMPER_RE = re.compile(r"\b([1-8]\d{3})[\s-](T\d{1,4}|H\d{1,3})\b", re.IGNORECASE)
# Inconel nickel superalloys: "Inconel 718", "Inconel 625".
_INCONEL_RE = re.compile(r"\bInconel[\s-]*(\d{3,4}[A-Za-z]*)\b", re.IGNORECASE)
# Titanium alloys: base "Ti" followed by weighted alloying elements ("Ti-6Al-4V").
_TI_RE = re.compile(r"\bTi(?:-\d+(?:\.\d+)?[A-Z][a-z]?){1,6}\b")

# AISI/SAE stainless designations (curated so arbitrary 3-digit numbers do not
# masquerade as grades). Optional L / N / H / Ti chemistry suffix.
_STAINLESS: frozenset[str] = frozenset(
    {
        "201",
        "202",
        "301",
        "302",
        "303",
        "304",
        "305",
        "308",
        "309",
        "310",
        "316",
        "317",
        "321",
        "330",
        "347",
        "384",
        "410",
        "416",
        "420",
        "430",
        "431",
        "440",
        "446",
        "904",
    }
)
_SS_RE = re.compile(r"\b(\d{3})(LN|Ti|L|N|H)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class GradeMatch:
    """A recognized standard alloy grade (§6.4)."""

    grade: str
    system: str
    temper: str | None
    source_span: str

    def as_dict(self) -> dict:
        """Serialize to a plain dict (all fields, ``None`` preserved)."""
        return asdict(self)


def parse_grade(text: str) -> GradeMatch | None:
    """Parse the leftmost standard alloy grade (with optional temper), else None.

    Разбор стандартной марки сплава с опциональным состоянием (temper).
    """
    if not text:
        return None
    cands: list[tuple[int, int, GradeMatch]] = []

    for m in _AA_PREFIX_RE.finditer(text):
        temper = m.group(2).upper() if m.group(2) else None
        cands.append((m.start(), m.end(), GradeMatch(m.group(1), "AA", temper, m.group(0))))

    for m in _AL_TEMPER_RE.finditer(text):
        temper = m.group(2).upper()
        cands.append((m.start(), m.end(), GradeMatch(m.group(1), "AA", temper, m.group(0))))

    for m in _INCONEL_RE.finditer(text):
        cands.append((m.start(), m.end(), GradeMatch(m.group(1), "Inconel", None, m.group(0))))

    for m in _TI_RE.finditer(text):
        elems = re.findall(r"[A-Z][a-z]?", m.group(0)[2:])  # drop the leading "Ti"
        if elems and all(e in _ELEMENTS for e in elems):
            cands.append((m.start(), m.end(), GradeMatch(m.group(0), "Ti", None, m.group(0))))

    for m in _SS_RE.finditer(text):
        base = m.group(1)
        if base not in _STAINLESS:
            continue
        raw = m.group(2)
        suffix = "Ti" if raw and raw.lower() == "ti" else (raw.upper() if raw else "")
        cands.append((m.start(), m.end(), GradeMatch(base + suffix, "AISI", None, m.group(0))))

    if not cands:
        return None
    # Leftmost wins; on a tie the longest match wins.
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    return cands[0][2]


# ---------------------------------------------------------------------------
# Composition fractions (wt% / at% / balance)
# ---------------------------------------------------------------------------
_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_ELEM_TOK = r"[A-Z][a-z]?|[А-Яа-яЁё]+"
# Fraction markers: qualified variants MUST precede the bare "%" so the plain
# percent only matches when neither weight nor atomic qualifier is present.
_MARK = r"wt\.?\s*%|масс\.?\s*%|мас\.?\s*%|ат\.?\s*%|at\.?\s*%|%"

_FRACTION_RE = re.compile(
    rf"(?:\b({_ELEM_TOK})\b\s+)?({_NUM})\s*({_MARK})(?:\s+\b({_ELEM_TOK})\b)?",
    re.IGNORECASE,
)
# "balance" / "bal." / "ост." remainder keyword, bounded by non-letters so a
# trailing dot is consumed cleanly.
_BAL_KW_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?:balance|bal\.?|ост\.?|остальное)(?![A-Za-zА-Яа-яЁё])",
    re.IGNORECASE,
)
_ELEM_BEFORE_RE = re.compile(rf"({_ELEM_TOK})\s*$")
_ELEM_AFTER_RE = re.compile(rf"^\s*({_ELEM_TOK})")


@dataclass(frozen=True)
class ElementFraction:
    """A single element fraction mention (§6.4)."""

    element: str | None
    value: float | None
    fraction_type: str  # "wt" | "at" | "unknown"
    is_balance: bool = False

    def as_dict(self) -> dict:
        """Serialize to a plain dict (all fields, ``None`` preserved)."""
        return asdict(self)


def _sym(token: str | None) -> str | None:
    """Resolve a token to a canonical element symbol (EN symbol or RU name)."""
    if not token:
        return None
    if token in _ELEMENTS:
        return token
    return _RU_ELEMENT.get(token.lower())


def _fraction_type(mark: str) -> str:
    """Classify a percent marker as weight / atomic / unknown fraction."""
    m = mark.lower().replace(" ", "").replace(".", "")
    if m.startswith(("wt", "мас", "масс")):
        return "wt"
    if m.startswith(("at", "ат")):
        return "at"
    return "unknown"


def _balance_element(text: str, start: int, end: int) -> str | None:
    """Find the element bound to a balance keyword (preferring the one before)."""
    before = _ELEM_BEFORE_RE.search(text[:start])
    if before and (sym := _sym(before.group(1))):
        return sym
    after = _ELEM_AFTER_RE.match(text[end:])
    if after:
        return _sym(after.group(1))
    return None


def parse_composition_fractions(text: str) -> list[ElementFraction]:
    """Extract element fractions, tagging wt%/at%/unknown and balance remainders.

    Извлечение долей элементов с разметкой типа доли и признаком «остальное».
    """
    if not text:
        return []
    found: list[tuple[int, ElementFraction]] = []

    for m in _FRACTION_RE.finditer(text):
        element = _sym(m.group(4)) or _sym(m.group(1))
        if element is None:  # a bare percent with no adjacent element is not a fraction
            continue
        value = float(m.group(2).replace(",", "."))
        found.append(
            (m.start(), ElementFraction(element, value, _fraction_type(m.group(3)), False))
        )

    for m in _BAL_KW_RE.finditer(text):
        element = _balance_element(text, m.start(), m.end())
        if element is None:
            continue
        found.append((m.start(), ElementFraction(element, None, "unknown", True)))

    found.sort(key=lambda f: f[0])
    return [ef for _, ef in found]
