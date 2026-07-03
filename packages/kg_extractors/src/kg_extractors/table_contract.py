"""Table-extraction output contract — stable serialization boundary (§5.5).

The table extractor turns a parsed document's tables (таблицы из разобранных
документов) into structured records; this module defines the *contract* those
records cross when they leave extraction: a frozen :class:`TableCell` addressed
by ``(row_index, col_index)`` and a frozen :class:`TableExtract` bundling a
table's ``header`` + ``cells`` with its ``n_rows`` / ``n_cols`` dimensions and
``doc_id`` / ``page`` / ``caption`` provenance. The cell coordinates match the
Evidence anchor fields of §8.3 (``table_id`` / ``page`` / ``row_index`` /
``col_index``), so a cell can be cited straight from this record.

:func:`from_grid` builds a :class:`TableExtract` from a raw ``list[list[str]]``
grid — optionally peeling the first row off as the header — and computes the
dimensions and cells. :func:`cell_at` reads one body cell back by coordinate,
and :func:`to_jsonl` / :func:`from_jsonl` give a lossless JSONL round-trip.

Pure Python (``json`` / ``dataclasses`` only) so this boundary never pulls in an
LLM or optional ML stack.

Public API:

- :class:`TableCell`    — one addressable body cell (``as_dict`` / ``from_dict``);
- :class:`TableExtract` — a whole extracted table (``as_dict`` / ``from_dict``);
- :func:`from_grid`     — build a :class:`TableExtract` from a raw grid;
- :func:`cell_at`       — read one body cell by ``(row, col)`` (``None`` if absent);
- :func:`to_jsonl` / :func:`from_jsonl` — JSONL round-trip over a table list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


# --- one addressable cell (§5.5) -----------------------------------------------
@dataclass(frozen=True)
class TableCell:
    """One body cell of a table, addressed by its 0-based grid coordinate.

    Fields:

    - ``row_index`` — 0-based body-row index (the header row is *not* counted);
    - ``col_index`` — 0-based column index;
    - ``text``      — the cell's text (verbatim; «» for an empty ячейка).
    """

    row_index: int
    col_index: int
    text: str

    def as_dict(self) -> dict[str, object]:
        """Return the canonical, JSON-ready projection of this cell."""
        return {
            "row_index": self.row_index,
            "col_index": self.col_index,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TableCell:
        """Rebuild a :class:`TableCell` from a decoded mapping (inverse of ``as_dict``)."""
        return cls(
            row_index=int(data["row_index"]),  # type: ignore[arg-type]
            col_index=int(data["col_index"]),  # type: ignore[arg-type]
            text=str(data["text"]),
        )


# --- a whole extracted table (§5.5) --------------------------------------------
@dataclass(frozen=True)
class TableExtract:
    """One table crossing the extractor → graph boundary (§5.5).

    Fields:

    - ``table_id`` — stable unique id for this table (provenance / Evidence key);
    - ``doc_id``   — id of the source document the table came from;
    - ``page``     — 1-based source page number, or ``None`` when unknown;
    - ``n_rows``   — number of *body* rows (excludes the header row);
    - ``n_cols``   — number of columns (widest of header + body);
    - ``header``   — column headers («» each when no header row was present);
    - ``cells``    — the body cells as :class:`TableCell` records;
    - ``caption``  — the table caption / подпись, or ``None`` when absent.
    """

    table_id: str
    doc_id: str
    page: int | None
    n_rows: int
    n_cols: int
    header: list[str]
    cells: list[TableCell]
    caption: str | None

    def as_dict(self) -> dict[str, object]:
        """Return the canonical, JSON-ready projection of this table.

        ``cells`` become plain dicts (never dataclass reprs) and ``header`` is
        copied, so the mapping is a pure ``str`` / ``int`` / ``list`` record.
        """
        return {
            "table_id": self.table_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "header": list(self.header),
            "cells": [c.as_dict() for c in self.cells],
            "caption": self.caption,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TableExtract:
        """Rebuild a :class:`TableExtract` from a decoded mapping (inverse of ``as_dict``).

        ``page`` and ``caption`` stay ``None`` when null / absent; ``header`` and
        ``cells`` default to empty when a key is missing.
        """
        page_raw = data.get("page")
        caption_raw = data.get("caption")
        header_raw = data.get("header") or []
        cells_raw = data.get("cells") or []
        return cls(
            table_id=str(data["table_id"]),
            doc_id=str(data["doc_id"]),
            page=None if page_raw is None else int(page_raw),  # type: ignore[arg-type]
            n_rows=int(data["n_rows"]),  # type: ignore[arg-type]
            n_cols=int(data["n_cols"]),  # type: ignore[arg-type]
            header=[str(h) for h in header_raw],  # type: ignore[union-attr]
            cells=[TableCell.from_dict(c) for c in cells_raw],  # type: ignore[union-attr]
            caption=None if caption_raw is None else str(caption_raw),
        )


def from_grid(
    table_id: str,
    doc_id: str,
    rows: list[list[str]],
    *,
    page: int | None = None,
    header_row: bool = True,
    caption: str | None = None,
) -> TableExtract:
    """Build a :class:`TableExtract` from a raw ``list[list[str]]`` grid (§5.5).

    When ``header_row`` is true (the default) the first grid row is peeled off as
    the ``header`` and the remaining rows become the body; when false the
    ``header`` is empty and *every* row is kept as body. ``n_rows`` counts body
    rows only and ``n_cols`` is the widest row (header included), so a ragged grid
    (неровная сетка) still reports a consistent width. Cells are emitted for each
    present body cell at its 0-based ``(row_index, col_index)``.

    An empty grid yields ``n_rows == n_cols == 0`` with no header and no cells.
    """
    grid = [list(r) for r in rows]
    if header_row and grid:
        header = [str(c) for c in grid[0]]
        body = grid[1:]
    else:
        header = []
        body = grid
    n_rows = len(body)
    widths = [len(header)] + [len(r) for r in body] if header else [len(r) for r in body]
    n_cols = max(widths, default=0)
    cells = [
        TableCell(row_index=r, col_index=c, text=str(value))
        for r, bodyrow in enumerate(body)
        for c, value in enumerate(bodyrow)
    ]
    return TableExtract(
        table_id=table_id,
        doc_id=doc_id,
        page=page,
        n_rows=n_rows,
        n_cols=n_cols,
        header=header,
        cells=cells,
        caption=caption,
    )


def cell_at(table: TableExtract, r: int, c: int) -> str | None:
    """Return the body cell text at ``(r, c)``, or ``None`` when there is none.

    Coordinates are 0-based into the body (the header is addressed separately via
    ``table.header``). A coordinate with no matching cell — out of range or an
    absent ragged cell — yields ``None`` rather than raising.
    """
    for cell in table.cells:
        if cell.row_index == r and cell.col_index == c:
            return cell.text
    return None


def to_jsonl(tables: list[TableExtract]) -> str:
    """Serialize tables to JSONL — one JSON object per line (§5.5).

    An empty list yields the empty string (no trailing newline). Each line is
    ``table.as_dict()`` with ``ensure_ascii=False`` so RU text stays
    human-readable, and lines are newline-joined without a trailing newline.
    """
    return "\n".join(json.dumps(t.as_dict(), ensure_ascii=False) for t in tables)


def from_jsonl(s: str) -> list[TableExtract]:
    """Parse JSONL back into tables — inverse of :func:`to_jsonl` (§5.5).

    Blank lines are skipped, so round-tripping is lossless regardless of a
    trailing newline. An empty / whitespace-only string yields ``[]``.
    """
    out: list[TableExtract] = []
    for line in s.splitlines():
        if not line.strip():
            continue
        out.append(TableExtract.from_dict(json.loads(line)))
    return out
