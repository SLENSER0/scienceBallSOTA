"""Table-row linearizer — ``table_row`` chunks with header context (§5.9).

A table is only meaningful when a cell knows *which column* it lives in. This
module turns a table's rows into standalone :class:`RowChunk` texts that embed
the column headers, so each row reads on its own — «материал=Ti; твёрдость=350»
— without the reader having to look back at the header row. Every chunk carries
``table_id`` / ``row_index`` anchors (§8.3) so it can be traced back to its cell
in the source table.

Ragged rows (shorter than the header list) are padded with empty cells, and
empty cells are dropped from the linearized text (but still present as keys in
:attr:`RowChunk.cells`), so a partly-filled row stays valid and queryable.

Pure Python (``dataclasses`` only) — this boundary never pulls in an LLM or any
optional ML stack.

Public API:

- :class:`RowChunk`       — frozen per-row record with ``as_dict``;
- :func:`linearize_row`   — join non-empty ``header=cell`` pairs with ``'; '``;
- :func:`rows_to_chunks`  — a table's rows → ``list[RowChunk]`` (row_index 0..N).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Separator between ``header=cell`` pairs in a linearized row text.
_PAIR_SEP = "; "
#: Separator between a header name and its cell value.
_KV_SEP = "="


def linearize_row(headers: list[str], row: list[str]) -> str:
    """Join non-empty ``header=cell`` pairs of ``row`` with ``'; '``.

    Pairs whose cell is empty (or whitespace-only) are skipped, so
    ``linearize_row(['a', 'b'], ['1', ''])`` → ``'a=1'`` and
    ``linearize_row(['материал', 'твёрдость'], ['Ti', '350'])`` →
    ``'материал=Ti; твёрдость=350'``. A row longer than ``headers`` has its
    extra cells ignored; a shorter row simply contributes fewer pairs.
    """
    pairs: list[str] = []
    for header, cell in zip(headers, row, strict=False):
        text = "" if cell is None else str(cell).strip()
        if not text:
            continue
        pairs.append(f"{header}{_KV_SEP}{text}")
    return _PAIR_SEP.join(pairs)


@dataclass(frozen=True)
class RowChunk:
    """A single ``table_row`` chunk — one linearized table row (§5.9).

    ``text`` is the header-embedded linearization (see :func:`linearize_row`);
    ``cells`` maps every header to its (possibly empty) cell so callers can read
    columns structurally. ``table_id`` + ``row_index`` are the §8.3 anchors back
    to the source table cell; ``page`` is the 1-based source page if known.
    """

    table_id: str
    row_index: int
    text: str
    cells: dict[str, str] = field(default_factory=dict)
    page: int | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a plain-``dict`` projection (canonical field order)."""
        return {
            "table_id": self.table_id,
            "row_index": self.row_index,
            "text": self.text,
            "cells": dict(self.cells),
            "page": self.page,
        }


def rows_to_chunks(
    table_id: str,
    headers: list[str],
    rows: list[list[str]],
    page: int | None = None,
) -> list[RowChunk]:
    """Turn a table's ``rows`` into :class:`RowChunk` records (row_index 0..N).

    Each row is padded to ``len(headers)`` with empty cells so ragged rows keep
    all header keys in :attr:`RowChunk.cells`; the linearized ``text`` embeds the
    column headers for standalone context. ``row_index`` counts from ``0``. An
    empty ``rows`` list yields ``[]``.
    """
    chunks: list[RowChunk] = []
    width = len(headers)
    for row_index, row in enumerate(rows):
        padded = list(row[:width]) + [""] * (width - len(row))
        cells = {
            header: ("" if cell is None else str(cell))
            for header, cell in zip(headers, padded, strict=True)
        }
        chunks.append(
            RowChunk(
                table_id=table_id,
                row_index=row_index,
                text=linearize_row(headers, padded),
                cells=cells,
                page=page,
            )
        )
    return chunks
