"""Table structure enrichment — per-column type profiling (§5.7).

Extracted tables arrive as a header row plus a list of string cell rows. Before
the values feed the property extractors, it helps to know *what kind* of column
each one is: a free-text label column (``Material``), a numeric measurement
column (``Hardness (HV)``), an all-blank filler, or a messy ``mixed`` column
that needs a human. This module folds a raw table into a frozen
:class:`TableProfile` — one :class:`ColumnProfile` per column — using nothing but
the string cells (чистый Python, без LLM и без I/O).

Numeric detection (числовые ячейки):

* plain integers / floats — ``148``, ``3.14``, ``-5``;
* scientific notation — ``1.2e3``, ``2.5E-4``;
* ranges — ``200-300`` counts as numeric (its midpoint ``250`` is a number).

A column's ``numeric_fraction`` is the share of *non-empty* cells that parse as a
number. The type follows from it:

* ``>= 0.8``              → :attr:`ColumnType.NUMERIC`;
* every cell blank        → :attr:`ColumnType.EMPTY`;
* ``0.2 < frac < 0.8``    → :attr:`ColumnType.MIXED`;
* otherwise               → :attr:`ColumnType.CATEGORICAL`.

Unit hint (единица измерения) is a token read from the header only:

* parenthesized — ``Hardness (HV)`` → ``HV``;
* trailing after a comma — ``σ, МПа`` → ``МПа`` (RU/EN both work).

Public API:

- :class:`ColumnType`    — ``numeric`` / ``categorical`` / ``empty`` / ``mixed``;
- :class:`ColumnProfile` — frozen per-column record with :meth:`as_dict`;
- :class:`TableProfile`  — frozen table record with :meth:`as_dict`;
- :func:`profile_columns` — profile ``headers`` + ``rows`` into a table profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# Numeric threshold: at/above -> NUMERIC; the low edge -> CATEGORICAL below it.
_NUMERIC_HI = 0.8
_NUMERIC_LO = 0.2

# Plain int/float with optional sign and scientific exponent (1.2e3, -2.5E-4).
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
# A range like '200-300' or '1.5 – 2.0' (ASCII hyphen or unicode dashes).
_RANGE_RE = re.compile(
    r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*[-–—]\s*"
    r"([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)$"
)
# Parenthesized unit in a header: 'Hardness (HV)' -> 'HV'.
_PAREN_UNIT_RE = re.compile(r"\(([^)]+)\)\s*$")
# Trailing comma unit in a header: 'σ, МПа' -> 'МПа'.
_COMMA_UNIT_RE = re.compile(r",\s*([^,]+?)\s*$")


class ColumnType(StrEnum):
    """Kind of a table column, inferred from its cells (§5.7).

    A :class:`~enum.StrEnum`, so a :class:`ColumnType` serializes as its bare
    string value (``"numeric"`` and so on) with no ``ColumnType.`` prefix.
    """

    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    EMPTY = "empty"
    MIXED = "mixed"


def _is_number(cell: str) -> bool:
    """Return whether ``cell`` parses as a number or a numeric range (§5.7).

    A plain int/float/scientific literal counts, and so does a range such as
    ``200-300`` (its midpoint is a number). Whitespace is stripped first.
    """
    text = cell.strip()
    if not text:
        return False
    if _NUMBER_RE.match(text):
        return True
    return _RANGE_RE.match(text) is not None


def _detect_unit(header: str) -> str | None:
    """Read a unit token out of a column ``header``, or ``None`` (§5.7).

    Parenthesized units win (``Hardness (HV)`` -> ``HV``); otherwise a trailing
    comma clause is used (``σ, МПа`` -> ``МПа``). RU and EN are both handled.
    """
    paren = _PAREN_UNIT_RE.search(header)
    if paren:
        unit = paren.group(1).strip()
        return unit or None
    comma = _COMMA_UNIT_RE.search(header)
    if comma:
        unit = comma.group(1).strip()
        return unit or None
    return None


@dataclass(frozen=True)
class ColumnProfile:
    """Profile of a single table column (§5.7).

    Fields
    ------
    index
        Zero-based column position in the header row (номер столбца).
    header
        The raw header string for this column (заголовок).
    col_type
        Inferred :class:`ColumnType` (тип столбца).
    numeric_fraction
        Share of non-empty cells that parse as a number, in ``[0.0, 1.0]``;
        ``0.0`` for an all-blank column (доля числовых ячеек).
    unit_hint
        Unit token read from the header, or ``None`` (единица измерения).
    """

    index: int
    header: str
    col_type: ColumnType
    numeric_fraction: float
    unit_hint: str | None

    def as_dict(self) -> dict[str, object]:
        """Return a plain-``dict`` projection of this column profile (§5.7)."""
        return {
            "index": self.index,
            "header": self.header,
            "col_type": str(self.col_type),
            "numeric_fraction": self.numeric_fraction,
            "unit_hint": self.unit_hint,
        }


@dataclass(frozen=True)
class TableProfile:
    """Profile of a whole table — one entry per column (§5.7).

    Fields
    ------
    columns
        The per-column :class:`ColumnProfile` records, in header order
        (профили столбцов).
    """

    columns: tuple[ColumnProfile, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a plain-``dict`` projection of the table profile (§5.7)."""
        return {"columns": [column.as_dict() for column in self.columns]}


def _classify(numeric_fraction: float, all_empty: bool) -> ColumnType:
    """Map a ``numeric_fraction`` (+ all-blank flag) to a :class:`ColumnType`."""
    if all_empty:
        return ColumnType.EMPTY
    if numeric_fraction >= _NUMERIC_HI:
        return ColumnType.NUMERIC
    if _NUMERIC_LO < numeric_fraction < _NUMERIC_HI:
        return ColumnType.MIXED
    return ColumnType.CATEGORICAL


def profile_columns(headers: list[str], rows: list[list[str]]) -> TableProfile:
    """Profile each column of a table into a :class:`TableProfile` (§5.7).

    For every column the fraction of *non-empty* cells that parse as a number
    (int / float / ``1.2e3`` / ``200-300`` range) decides its
    :class:`ColumnType`: ``NUMERIC`` at ``>= 0.8``, ``EMPTY`` when every cell is
    blank, ``MIXED`` when strictly between ``0.2`` and ``0.8``, else
    ``CATEGORICAL``. ``unit_hint`` comes from the header. Ragged rows shorter
    than ``headers`` are padded with blanks, so a short row never crashes
    (короткие строки дополняются пустыми ячейками).
    """
    profiles: list[ColumnProfile] = []
    for index, header in enumerate(headers):
        cells = [row[index] if index < len(row) else "" for row in rows]
        non_empty = [cell for cell in cells if cell.strip()]
        all_empty = not non_empty
        if all_empty:
            numeric_fraction = 0.0
        else:
            numeric = sum(1 for cell in non_empty if _is_number(cell))
            numeric_fraction = numeric / len(non_empty)
        col_type = _classify(numeric_fraction, all_empty)
        profiles.append(
            ColumnProfile(
                index=index,
                header=header,
                col_type=col_type,
                numeric_fraction=numeric_fraction,
                unit_hint=_detect_unit(header),
            )
        )
    return TableProfile(columns=tuple(profiles))
