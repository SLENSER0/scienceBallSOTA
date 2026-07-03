"""Row/dict -> CSV serialisation — экспорт строк в CSV (§22.5).

A tiny, dependency-free CSV writer built on the stdlib :mod:`csv` module. Two
entry points cover the common cases:

* :func:`rows_to_csv` — serialise a list of dict rows against an *explicit*
  column order (``columns``); a column absent from a row (or present with
  ``None``) renders as an empty cell (``""``).
* :func:`dicts_to_csv` — the same, but the column order is *inferred* from the
  data: the union of every dict's keys in **first-seen order** (stable, a pure
  function of the input — no sorting surprises, порядок колонок стабилен).

Both delegate cell quoting to the stdlib writer, so commas, double-quotes and
embedded newlines round-trip per RFC 4180 — экранирование разделителей. Output
is UTF-8-safe text (Cyrillic passes through unchanged) and uses ``"\\n"`` line
terminators for deterministic, hand-checkable output. Empty input with no
columns yields ``""``.
"""

from __future__ import annotations

import csv
import io
from typing import Any

__all__ = ["infer_columns", "rows_to_csv", "dicts_to_csv"]


def _cell(value: Any) -> str:
    """Render one cell value; ``None`` (incl. a missing key) -> empty string."""
    return "" if value is None else str(value)


def infer_columns(dicts: list[dict[str, Any]]) -> list[str]:
    """Union of every dict's keys in first-seen order (§22.5).

    Deterministic and stable: a key is placed at the position where it is first
    encountered while scanning ``dicts`` in order, then rows, so the column list
    is a pure function of the input (no ``set`` reordering, no sorting).
    """
    columns: list[str] = []
    seen: set[str] = set()
    for row in dicts:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def rows_to_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Serialise ``rows`` to a CSV string with a header row (§22.5).

    ``columns`` fixes the header and per-row cell order; when ``None`` it is
    inferred via :func:`infer_columns` (first-seen union of keys). Uses the
    stdlib :mod:`csv` writer, so commas, double-quotes and embedded newlines in
    a cell are quoted/escaped correctly (RFC 4180). ``"\\n"`` line terminators
    keep the output hand-checkable.

    The first line is exactly ``columns``; each following line is one row, in
    ``columns`` order. A column absent from a row (or ``None``) yields an empty
    cell. With ``rows == []`` and no columns the result is ``""``; with columns
    it is the header line only.
    """
    cols = infer_columns(rows) if columns is None else list(columns)
    if not cols:
        return ""
    buf = io.StringIO()
    # lineterminator="\n": avoid the default "\r\n" so splitlines() is exact.
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(cols)
    for row in rows:
        writer.writerow([_cell(row.get(col)) for col in cols])
    return buf.getvalue()


def dicts_to_csv(dicts: list[dict[str, Any]]) -> str:
    """Serialise ``dicts`` to CSV with columns inferred from the data (§22.5).

    Convenience wrapper over :func:`rows_to_csv` with ``columns=None``: the
    header is the first-seen union of every dict's keys (see
    :func:`infer_columns`). Empty input yields ``""``.
    """
    return rows_to_csv(dicts, columns=None)
