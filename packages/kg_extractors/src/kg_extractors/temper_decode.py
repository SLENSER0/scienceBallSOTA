"""Temper-designation decoder (§6.4 / §6.5).

Декодер обозначений состояния (temper) сплавов в канонические операции.

:func:`kg_extractors.alloy_grades.parse_grade` only *captures* the temper token
(``T6`` / ``T651`` / ``H14`` / ``O`` / ``F`` / ``W``) — it never decodes what that
token means in terms of processing. This module closes that gap: it maps the
Aluminum-Association temper designations to an **ordered** tuple of canonical
processing operations, drawn from the same controlled vocabulary as
:mod:`kg_extractors.processing_vocab`:

- ``solution_treatment`` — растворная (закалка) термообработка
- ``natural_aging`` — естественное старение
- ``artificial_aging`` — искусственное старение
- ``annealing`` — отжиг
- ``strain_hardening`` — деформационное упрочнение (наклёп)
- ``stress_relief`` — снятие остаточных напряжений

The order of the returned operations mirrors the physical processing sequence,
so e.g. ``T6`` decodes to ``(solution_treatment, artificial_aging)`` and the
stress-relieved variant ``T651`` appends ``stress_relief`` after the two ``T6``
operations. Pure python, regex only — no other dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical processing-operation ids (mirror kg_extractors.processing_vocab).
SOLUTION_TREATMENT = "solution_treatment"
NATURAL_AGING = "natural_aging"
ARTIFICIAL_AGING = "artificial_aging"
ANNEALING = "annealing"
STRAIN_HARDENING = "strain_hardening"
STRESS_RELIEF = "stress_relief"


@dataclass(frozen=True)
class TemperMeaning:
    """Decoded meaning of a temper designation (§6.4 / §6.5).

    ``operations`` is the ordered tuple of canonical processing-operation ids
    implied by the temper (empty for ``F`` as-fabricated).
    """

    code: str
    operations: tuple[str, ...]
    description: str

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict (``operations`` as a list)."""
        return {
            "code": self.code,
            "operations": list(self.operations),
            "description": self.description,
        }


# Basic T-temper digit (first digit after ``T``) -> ordered operation sequence.
# Sequences follow the physical processing order of ANSI H35.1 / AA tempers.
_T_BASE: dict[str, tuple[str, ...]] = {
    "1": (NATURAL_AGING,),
    "2": (STRAIN_HARDENING, NATURAL_AGING),
    "3": (SOLUTION_TREATMENT, STRAIN_HARDENING, NATURAL_AGING),
    "4": (SOLUTION_TREATMENT, NATURAL_AGING),
    "5": (ARTIFICIAL_AGING,),
    "6": (SOLUTION_TREATMENT, ARTIFICIAL_AGING),
    "7": (SOLUTION_TREATMENT, ARTIFICIAL_AGING),
    "8": (SOLUTION_TREATMENT, STRAIN_HARDENING, ARTIFICIAL_AGING),
    "9": (SOLUTION_TREATMENT, ARTIFICIAL_AGING, STRAIN_HARDENING),
    "10": (STRAIN_HARDENING, ARTIFICIAL_AGING),
}

_T_DESC: dict[str, str] = {
    "1": "cooled from an elevated-temperature shaping process and naturally aged",
    "2": "cooled from shaping, cold worked and naturally aged",
    "3": "solution heat-treated, cold worked and naturally aged",
    "4": "solution heat-treated and naturally aged to a stable condition",
    "5": "cooled from an elevated-temperature shaping process and artificially aged",
    "6": "solution heat-treated and artificially aged",
    "7": "solution heat-treated and overaged/stabilized (artificially aged)",
    "8": "solution heat-treated, cold worked and artificially aged",
    "9": "solution heat-treated, artificially aged and cold worked",
    "10": "cooled from shaping, cold worked and artificially aged",
}

# Basic H-temper first digit -> ordered operation sequence.
_H_BASE: dict[str, tuple[str, ...]] = {
    "1": (STRAIN_HARDENING,),
    "2": (STRAIN_HARDENING, ANNEALING),
    "3": (STRAIN_HARDENING, STRESS_RELIEF),
    "4": (STRAIN_HARDENING,),
}

_H_DESC: dict[str, str] = {
    "1": "strain-hardened only",
    "2": "strain-hardened and partially annealed",
    "3": "strain-hardened and stabilized",
    "4": "strain-hardened and lacquered or painted",
}

_T_RE = re.compile(r"^T(10|\d)(\d*)$")
_H_RE = re.compile(r"^H(\d)(\d*)$")


def decode_temper(code: str) -> TemperMeaning | None:
    """Decode a temper designation into ordered canonical operations, else None.

    Декодирование обозначения состояния в упорядоченные канонические операции.

    Recognizes the bare-letter tempers ``F`` / ``O`` / ``W`` and the
    Aluminum-Association ``T``- and ``H``-series (including the ``…51`` /
    ``…52`` stress-relief variants that append ``stress_relief``). Returns
    ``None`` for an unrecognized designation.
    """
    if not code:
        return None
    c = str(code).strip().upper()
    if not c:
        return None

    if c == "F":
        return TemperMeaning(c, (), "as-fabricated — no special processing control")
    if c == "O":
        return TemperMeaning(c, (ANNEALING,), "annealed — softest, most workable condition")
    if c == "W":
        return TemperMeaning(
            c, (SOLUTION_TREATMENT,), "solution heat-treated — unstable, naturally aging"
        )

    m = _T_RE.match(c)
    if m:
        base, extra = m.group(1), m.group(2)
        ops = _T_BASE.get(base)
        if ops is None:
            return None
        desc = f"T{base}: {_T_DESC[base]}"
        # A trailing digit group beginning with ``5`` denotes stress relief
        # (…51 by stretching, …52 by compressing, …510/511 combinations).
        if extra and extra[0] == "5":
            ops = (*ops, STRESS_RELIEF)
            desc = f"{desc}; stress-relieved (variant {extra})"
        return TemperMeaning(c, ops, desc)

    m = _H_RE.match(c)
    if m:
        first = m.group(1)
        ops = _H_BASE.get(first)
        if ops is None:
            return None
        desc = f"H{first}x: {_H_DESC[first]}"
        return TemperMeaning(c, ops, desc)

    return None
