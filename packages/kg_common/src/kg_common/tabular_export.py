"""Comparison-table export to CSV / Markdown / XLSX (§24.16).

Экспорт таблиц сравнения (comparison-table export) into three portable,
permissive-licence formats:

* **CSV**       — pure stdlib :mod:`csv` (no dependency), UTF-8, RU-safe.
* **Markdown**  — a GitHub-flavoured table (pipes + a ``---`` separator row).
* **XLSX**      — via :mod:`openpyxl` (MIT), *import-guarded*: if the optional
  dependency is absent we raise :class:`ExportUnavailable` instead of failing
  at import time, so callers that never touch XLSX pay nothing.

Only permissive-licence backends are used (stdlib + openpyxl[MIT], §7.5
allowlist). PDF export is deliberately **not** provided — ``reportlab`` is BSD
and outside the §7.5 allowlist.

Cell rendering is uniform across all three formats: a column missing from a
row (or present with ``None``) renders as an empty cell (``""``); every other
value is stringified with :func:`str`. Values containing separators (commas,
quotes, pipes, newlines) are escaped per each format's own rules so the output
round-trips — экранирование разделителей.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ExportUnavailable(RuntimeError):
    """Requested export backend is not installed — бэкенд экспорта недоступен (§24.16).

    Raised by :func:`to_xlsx` when the optional :mod:`openpyxl` dependency
    cannot be imported. CSV and Markdown never raise this (stdlib-only).
    """


def _cell(value: Any) -> str:
    """Render one cell value; ``None`` (incl. missing keys) -> empty string."""
    return "" if value is None else str(value)


def to_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Serialise ``rows`` to a CSV string with a header row (§24.16).

    Uses the stdlib :mod:`csv` writer, so commas, double-quotes and embedded
    newlines inside a cell are quoted/escaped correctly (RFC 4180). The output
    is UTF-8-safe text (Cyrillic passes through unchanged) and uses ``"\\n"``
    line terminators for deterministic, hand-checkable output.

    The first line is exactly ``columns``; each subsequent line is one row, in
    ``columns`` order. A column absent from a row (or ``None``) yields an empty
    cell. With ``rows == []`` the result is the header line only.
    """
    buf = io.StringIO()
    # lineterminator="\n": avoid the default "\r\n" so splitlines() is exact.
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([_cell(row.get(col)) for col in columns])
    return buf.getvalue()


def _md_cell(value: Any) -> str:
    """Render one Markdown cell: escape pipes, flatten newlines to spaces."""
    text = _cell(value)
    # A raw "|" would break the table; newlines would split the row.
    return text.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def rows_to_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Render ``rows`` as a GitHub-flavoured Markdown table (§24.16).

    Layout is a header line, a ``---`` separator line, then one line per row::

        | name | value |
        | --- | --- |
        | медь | 8.96 |

    Pipes inside a cell are escaped (``\\|``) and newlines are flattened to
    spaces so a cell never breaks the row. The result has ``2 + len(rows)``
    lines (header + separator + N) and no trailing newline.
    """
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_md_cell(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def to_xlsx(rows: list[dict[str, Any]], columns: list[str], path: str | Path) -> Path:
    """Write ``rows`` to an ``.xlsx`` workbook at ``path`` (§24.16).

    Import-guarded: :mod:`openpyxl` (MIT) is imported lazily and, if missing,
    :class:`ExportUnavailable` is raised — the rest of the module (CSV /
    Markdown) stays usable without it. The first worksheet row is exactly
    ``columns``; each following row is one record in ``columns`` order, with
    missing/``None`` cells written as empty strings.

    Returns the :class:`~pathlib.Path` that was written.
    """
    try:
        import openpyxl
    except ImportError as exc:  # optional dep — degrade gracefully (§24.16)
        raise ExportUnavailable("openpyxl not installed") from exc

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(columns))
    for row in rows:
        sheet.append([_cell(row.get(col)) for col in columns])
    out = Path(path)
    workbook.save(str(out))
    return out


@dataclass(frozen=True)
class ComparisonExport:
    """A comparison table bound to its column order — таблица сравнения (§24.16).

    Convenience wrapper that binds ``rows`` + ``columns`` once and exposes the
    three format renderers as methods, so a caller does not repeat the column
    list per format. Immutable (frozen) so it can be passed around safely.
    """

    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_csv(self) -> str:
        """CSV string for this table (see :func:`to_csv`)."""
        return to_csv(self.rows, self.columns)

    def to_markdown(self) -> str:
        """GitHub Markdown table for this table (see :func:`rows_to_markdown_table`)."""
        return rows_to_markdown_table(self.rows, self.columns)

    def to_xlsx(self, path: str | Path) -> Path:
        """Write an XLSX workbook for this table (see :func:`to_xlsx`)."""
        return to_xlsx(self.rows, self.columns, path)

    def as_dict(self) -> dict[str, Any]:
        """Structured, JSON-friendly view of the bound table."""
        return {
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
        }
