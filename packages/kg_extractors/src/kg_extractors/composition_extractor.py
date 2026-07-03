"""Chemical-composition extraction from prose (§6.4).

Finds alloy/material composition mentions in RU/EN text and returns structured
element fractions with source spans (evidence-first). Two patterns:

- **dash notation** — ``Al-4Cu-1Mg`` / ``Fe-18Cr-8Ni`` / ``Ni-Cr-Mo`` (base
  element first, optional numeric weight before each subsequent element);
- **element-percent** — ``Cu 99.9%`` / ``медь 99,9 %`` / ``Fe: 65, Cr: 18, Ni: 8``.

Element symbols are validated against the periodic table so junk like ``Xx`` is
rejected. Deterministic + dependency-light (regex only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Periodic-table symbols (metallurgy-relevant coverage; longest-first not needed
# because the regex anchors on capital-letter boundaries).
_ELEMENTS: frozenset[str] = frozenset(
    [
        "H",
        "He",
        "Li",
        "Be",
        "B",
        "C",
        "N",
        "O",
        "F",
        "Ne",
        "Na",
        "Mg",
        "Al",
        "Si",
        "P",
        "S",
        "Cl",
        "Ar",
        "K",
        "Ca",
        "Sc",
        "Ti",
        "V",
        "Cr",
        "Mn",
        "Fe",
        "Co",
        "Ni",
        "Cu",
        "Zn",
        "Ga",
        "Ge",
        "As",
        "Se",
        "Br",
        "Kr",
        "Rb",
        "Sr",
        "Y",
        "Zr",
        "Nb",
        "Mo",
        "Tc",
        "Ru",
        "Rh",
        "Pd",
        "Ag",
        "Cd",
        "In",
        "Sn",
        "Sb",
        "Te",
        "I",
        "Xe",
        "Cs",
        "Ba",
        "La",
        "Ce",
        "Pr",
        "Nd",
        "Pm",
        "Sm",
        "Eu",
        "Gd",
        "Tb",
        "Dy",
        "Ho",
        "Er",
        "Tm",
        "Yb",
        "Lu",
        "Hf",
        "Ta",
        "W",
        "Re",
        "Os",
        "Ir",
        "Pt",
        "Au",
        "Hg",
        "Tl",
        "Pb",
        "Bi",
        "Po",
        "At",
        "Rn",
        "Th",
        "U",
    ]
)

# RU element names → symbol (common metallurgy elements).
_RU_ELEMENT = {
    "медь": "Cu",
    "железо": "Fe",
    "никель": "Ni",
    "хром": "Cr",
    "алюминий": "Al",
    "цинк": "Zn",
    "олово": "Sn",
    "свинец": "Pb",
    "титан": "Ti",
    "магний": "Mg",
    "кремний": "Si",
    "марганец": "Mn",
    "молибден": "Mo",
    "вольфрам": "W",
    "кобальт": "Co",
    "серебро": "Ag",
    "золото": "Au",
    "углерод": "C",
    "сера": "S",
}

# base + one-or-more (optional number)(element) segments: Al-4Cu-1Mg, Fe-18Cr-8Ni
_DASH_RE = re.compile(r"\b([A-Z][a-z]?)(?:[-–](?:\d+\.?\d*)?[A-Z][a-z]?){1,8}\b")
_SEGMENT_RE = re.compile(r"(\d+\.?\d*)?([A-Z][a-z]?)")
_PCT_RE = re.compile(
    r"\b([A-Z][a-z]?|[А-Яа-яё]+)\s*[:\-]?\s*(\d+[.,]?\d*)\s*(?:%|мас|wt)", re.IGNORECASE
)


@dataclass
class CompositionMention:
    text: str
    span: tuple[int, int]
    base_element: str | None
    elements: dict[str, float | None] = field(default_factory=dict)
    kind: str = "dash"  # "dash" | "percent"

    def element_symbols(self) -> list[str]:
        return sorted(self.elements)


def _valid(sym: str) -> bool:
    return sym in _ELEMENTS


def _parse_dash(match: re.Match) -> CompositionMention | None:
    raw = match.group(0)
    segs = _SEGMENT_RE.findall(raw)
    elements: dict[str, float | None] = {}
    base: str | None = None
    for i, (num, sym) in enumerate(segs):
        if not _valid(sym):
            return None
        if i == 0 and not num:
            base = sym
            elements[sym] = None
        else:
            elements[sym] = float(num) if num else None
    if len(elements) < 2:  # a lone symbol is not a composition
        return None
    return CompositionMention(raw, match.span(), base, elements, "dash")


def extract_compositions(text: str) -> list[CompositionMention]:
    """Extract composition mentions (dash notation + element-percent) with spans."""
    out: list[CompositionMention] = []
    seen: set[tuple[int, int]] = set()

    for m in _DASH_RE.finditer(text or ""):
        cm = _parse_dash(m)
        if cm and cm.span not in seen:
            seen.add(cm.span)
            out.append(cm)

    # element-percent runs: collect consecutive "<elem> <num>%" into one mention
    pct: dict[str, float | None] = {}
    start: int | None = None
    end = 0
    for m in _PCT_RE.finditer(text or ""):
        token, num = m.group(1), m.group(2)
        sym = token if _valid(token) else _RU_ELEMENT.get(token.lower())
        if not sym:
            continue
        # break the run if there's a big gap between matches (different sentence)
        if start is not None and m.start() - end > 40:
            _flush_pct(pct, start, end, text, seen, out)
            pct, start = {}, None
        pct[sym] = float(num.replace(",", "."))
        start = m.start() if start is None else start
        end = m.end()
    _flush_pct(pct, start, end, text, seen, out)

    out.sort(key=lambda c: c.span[0])
    return out


def _flush_pct(
    pct: dict,
    start: int | None,
    end: int,
    text: str,
    seen: set[tuple[int, int]],
    out: list[CompositionMention],
) -> None:
    if not pct or start is None:
        return
    span = (start, end)
    if span in seen:
        return
    seen.add(span)
    base = max(pct, key=lambda k: pct[k] or 0.0)
    out.append(CompositionMention(text[start:end], span, base, dict(pct), "percent"))
