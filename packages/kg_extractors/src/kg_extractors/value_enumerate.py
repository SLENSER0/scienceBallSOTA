"""§6.3 rule extractor — enumerate list/range values into discrete points (RU & EN).

Unlike :mod:`kg_extractors.numeric_normalize` / :mod:`kg_extractors.value_parser`, which
collapse a range «200–300» to a single midpoint, this module *expands* a measurement
phrase into the individual enumerated values required by §6.3, keeping a per-value
character span so each point can be anchored back to the source text::

    «180, 200, 220 °C» -> [180.0, 200.0, 220.0]   (kind='list')
    «2-4 h»            -> [2.0, 4.0]              (kind='range_endpoint')
    «150 HV»           -> [150.0]                 (kind='single')
    «1.5, 2.5 wt%»     -> [1.5, 2.5]              (kind='list')

Правило (RU): перечисление через запятую даёт ``kind='list'``; диапазон через тире —
``kind='range_endpoint'``; одиночное значение — ``kind='single'``. Каждое значение несёт
свой ``char_start``/``char_end`` в исходном тексте.

Pure-python / regex only. Numbers accept a decimal point or a decimal comma that is
directly adjacent to digits («2,5»); a comma followed by whitespace is treated as a list
separator, not a decimal mark. Leading signs are not consumed so a range dash «2-4» is
never mistaken for a negative number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Enumerated value record (§6.3)
# ---------------------------------------------------------------------------

_KINDS: frozenset[str] = frozenset({"single", "list", "range_endpoint"})


@dataclass(frozen=True)
class EnumeratedValue:
    """One discrete value expanded from a §6.3 list/range phrase.

    ``value`` is the parsed magnitude; ``char_start`` / ``char_end`` are the half-open
    span of the numeric token in the source ``text`` (so ``text[char_start:char_end]``
    is the exact digits); ``kind`` is one of ``single`` / ``list`` / ``range_endpoint``.
    """

    value: float
    char_start: int
    char_end: int
    kind: str

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            msg = f"kind must be one of {sorted(_KINDS)}, got {self.kind!r}"
            raise ValueError(msg)

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict (value + span + kind)."""
        return {
            "value": self.value,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "kind": self.kind,
        }


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# A numeric token: digits with an optional decimal point/comma glued to the digits.
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Range separators between two numbers: hyphen / en-dash / em-dash / «to» / «до».
_RANGE_SEP_RE = re.compile(r"[-–—]|\bto\b|\bдо\b", re.IGNORECASE)
# List separators between numbers: comma or semicolon.
_LIST_SEP_RE = re.compile(r"[,;]")


def _to_float(token: str) -> float:
    """Parse a numeric token, folding a decimal comma to a point («2,5» -> 2.5)."""
    return float(token.replace(",", "."))


def _gap_kind(gap: str) -> str | None:
    """Classify the text between two adjacent numbers: ``list`` / ``range`` / ``None``."""
    if _LIST_SEP_RE.search(gap):
        return "list"
    if _RANGE_SEP_RE.search(gap):
        return "range"
    return None


# ---------------------------------------------------------------------------
# Public API (§6.3)
# ---------------------------------------------------------------------------


def enumerate_values(text: str, unit: str | None = None) -> list[EnumeratedValue]:
    """Expand a §6.3 measurement phrase into discrete :class:`EnumeratedValue` points.

    A single number yields one ``single`` value. Numbers joined by commas/semicolons
    yield ``list`` values. Exactly two numbers joined by a range dash («2-4», «2 to 4»,
    «2 до 4») yield two ``range_endpoint`` values. Empty / number-free text yields ``[]``.

    ``unit`` is accepted for call-site symmetry with the rest of the extractor pipeline;
    enumeration itself is unit-agnostic, so it is currently unused.
    """
    del unit  # reserved: enumeration does not depend on the (optional) unit
    if not text or not text.strip():
        return []

    matches = list(_NUM_RE.finditer(text))
    if not matches:
        return []

    if len(matches) == 1:
        m = matches[0]
        return [EnumeratedValue(_to_float(m.group()), m.start(), m.end(), "single")]

    gaps = [text[matches[i].end() : matches[i + 1].start()] for i in range(len(matches) - 1)]
    gap_kinds = [_gap_kind(g) for g in gaps]

    # Exactly two numbers joined by a range dash -> endpoints; else a discrete list.
    is_range = len(matches) == 2 and gap_kinds[0] == "range"
    kind = "range_endpoint" if is_range else "list"

    return [EnumeratedValue(_to_float(m.group()), m.start(), m.end(), kind) for m in matches]
