"""GOST Cyrillic alloy/steel grade parsing (mining-metallurgical domain, §24, §6.4).

Разбор кириллических марок сталей и сплавов по ГОСТ.

The sibling :mod:`kg_extractors.alloy_grades` recognizes Latin designations
(Aluminum-Association / AISI / Inconel / Ti) but NOT the Cyrillic GOST grades that
dominate Russian metallurgical R&D (``12Х18Н10Т``, ``40Х``, ``Ст3``, ``Д16``).

This module adds a single deterministic, dependency-light parser (regex only):

- :func:`parse_gost_grade` — recognizes the leftmost GOST designation in ``text``
  and decodes it into a :class:`GostGrade`. Structural alloy steels carry a leading
  1-2 digit carbon group (hundredths of a percent) followed by Cyrillic alloying
  letters, each optionally trailed by an approximate percent digit; plain carbon
  steels (``Ст3``) and wrought aluminum alloys (``Д16``) are classified by prefix.
- :func:`cyrillic_element_map` — the Cyrillic-letter → element-symbol table.

A designation must contain at least one digit to be recognized, which keeps ordinary
Russian prose (letters only) from being mistaken for a grade.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# Cyrillic alloying-letter → element-symbol table (§24)
# ---------------------------------------------------------------------------
# Х->Cr, Н->Ni, Г->Mn, С->Si, Т->Ti, М->Mo, Ф->V, Д->Cu.
_CYRILLIC_ELEMENTS: dict[str, str] = {
    "Х": "Cr",
    "Н": "Ni",
    "Г": "Mn",
    "С": "Si",
    "Т": "Ti",
    "М": "Mo",
    "Ф": "V",
    "Д": "Cu",
}

# Wrought-aluminum designation prefixes (duralumins / АМг / АМц …). Longest first so
# the alternation is greedy: e.g. ``АМг`` wins over a bare ``А``.
_ALUMINUM_PREFIXES: tuple[str, ...] = ("АМг", "АМц", "АД", "АК", "АВ", "Д", "В")

# A candidate token: optional leading carbon digits, then at least one Cyrillic
# letter, then any mix of Cyrillic letters / digits. Anchored on a Cyrillic letter
# so pure-Latin text ("hello world") never matches.
_TOKEN_RE = re.compile(r"\d*[А-Яа-яЁё][А-Яа-яЁё0-9]*")
# Plain carbon structural steel: "Ст3", "Ст3кп", … (no decoded carbon fraction).
_PLAIN_STEEL_RE = re.compile(r"^Ст\d", re.IGNORECASE)
_ALUMINUM_RE = re.compile(rf"^(?:{'|'.join(_ALUMINUM_PREFIXES)})\d")
# Leading 1-2 digit carbon group for structural alloy steels (hundredths of %).
_CARBON_RE = re.compile(r"^(\d{1,2})")
# One alloying letter followed by its optional approximate-percent digit group.
_ELEM_RE = re.compile(r"([А-Яа-яЁё])(\d*)")


@dataclass(frozen=True)
class GostGrade:
    """A decoded GOST alloy/steel grade (§6.4, §24)."""

    raw: str
    grade_type: str  # "steel" | "aluminum"
    normalized: str
    carbon_pct: float | None
    elements: dict[str, float | None]

    def as_dict(self) -> dict:
        """Serialize to a plain dict (all fields, ``None`` preserved)."""
        return asdict(self)


def cyrillic_element_map() -> dict[str, str]:
    """Return a fresh copy of the Cyrillic-letter → element-symbol table (§24).

    Кириллическая буква легирующего элемента → химический символ.
    """
    return dict(_CYRILLIC_ELEMENTS)


def _decode_elements(rest: str) -> dict[str, float | None]:
    """Decode a run of ``<letter><digits?>`` groups into element → percent."""
    elements: dict[str, float | None] = {}
    for m in _ELEM_RE.finditer(rest):
        symbol = _CYRILLIC_ELEMENTS.get(m.group(1).upper())
        if symbol is None:
            continue
        elements[symbol] = float(m.group(2)) if m.group(2) else None
    return elements


def _classify(token: str) -> GostGrade | None:
    """Decode one candidate token into a grade, or return ``None`` if not a grade."""
    if not any(ch.isdigit() for ch in token):  # real grades always carry a digit
        return None

    if _PLAIN_STEEL_RE.match(token):  # plain carbon steel: no decoded carbon fraction
        return GostGrade(token, "steel", token.upper(), None, {})

    if _ALUMINUM_RE.match(token):  # wrought-aluminum designation (e.g. Д16)
        return GostGrade(token, "aluminum", token.upper(), None, {})

    carbon: float | None = None
    rest = token
    if cm := _CARBON_RE.match(token):
        carbon = int(cm.group(1)) / 100
        rest = token[cm.end() :]

    elements = _decode_elements(rest)
    if carbon is None and not elements:  # neither a carbon nor an alloy signal
        return None
    return GostGrade(token, "steel", token.upper(), carbon, elements)


def parse_gost_grade(text: str) -> GostGrade | None:
    """Parse the leftmost GOST alloy/steel grade in ``text``, else ``None``.

    Разбор кириллической марки стали/сплава по ГОСТ (крайняя левая), иначе ``None``.
    """
    if not text:
        return None
    for m in _TOKEN_RE.finditer(text):
        if grade := _classify(m.group(0)):
            return grade
    return None
