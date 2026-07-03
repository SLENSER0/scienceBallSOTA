"""Table output-contract tests — serialization boundary (§5.5).

Hand-checked expectations over RU + EN tables: :func:`from_grid` peels the
header row and computes the right ``n_rows`` / ``n_cols`` / ``header``,
:func:`cell_at` reads a body cell back by coordinate (and yields ``None`` for a
missing one), ``header_row=False`` keeps every row as body, the JSONL
round-trip preserves every field, ``as_dict`` / ``from_dict`` are exact inverses
for both records, an empty grid collapses to zero dimensions, and the caption is
carried through untouched.
"""

from __future__ import annotations

import json

from kg_extractors.table_contract import (
    TableCell,
    TableExtract,
    cell_at,
    from_grid,
    from_jsonl,
    to_jsonl,
)

# A 3-row grid: header + two body rows (материал / твёрдость).
_GRID = [
    ["material", "твёрдость"],
    ["copper", "40"],
    ["iron", "60"],
]

_TABLE_FIELDS = {
    "table_id",
    "doc_id",
    "page",
    "n_rows",
    "n_cols",
    "header",
    "cells",
    "caption",
}


def test_from_grid_dims_and_header() -> None:
    table = from_grid("t1", "doc1", _GRID, page=3)
    # First row peeled off as header; two body rows, two columns.
    assert table.header == ["material", "твёрдость"]
    assert table.n_rows == 2
    assert table.n_cols == 2
    assert table.page == 3
    assert table.table_id == "t1"
    assert table.doc_id == "doc1"
    # Four body cells at their 0-based coordinates.
    assert len(table.cells) == 4
    assert TableCell(0, 0, "copper") in table.cells
    assert TableCell(1, 1, "60") in table.cells


def test_cell_at_returns_value() -> None:
    table = from_grid("t1", "doc1", _GRID)
    assert cell_at(table, 0, 0) == "copper"
    assert cell_at(table, 0, 1) == "40"
    assert cell_at(table, 1, 0) == "iron"
    assert cell_at(table, 1, 1) == "60"


def test_cell_at_missing_returns_none() -> None:
    table = from_grid("t1", "doc1", _GRID)
    # Row index past the last body row → None.
    assert cell_at(table, 2, 0) is None
    # Column index past the last column → None.
    assert cell_at(table, 0, 5) is None
    # Negative coordinate → None (no cell carries it).
    assert cell_at(table, -1, 0) is None


def test_header_row_false_keeps_all_rows() -> None:
    table = from_grid("t2", "doc1", _GRID, header_row=False)
    # No header peeled: every row is body.
    assert table.header == []
    assert table.n_rows == 3
    assert table.n_cols == 2
    assert cell_at(table, 0, 0) == "material"
    assert cell_at(table, 0, 1) == "твёрдость"
    assert cell_at(table, 2, 0) == "iron"


def test_ragged_grid_pads_width_and_reads_none() -> None:
    # Header is 3 wide; the single body row is only 1 wide (ragged / неровная).
    table = from_grid("t3", "doc1", [["a", "b", "c"], ["x"]])
    assert table.n_cols == 3
    assert table.n_rows == 1
    assert cell_at(table, 0, 0) == "x"
    # The absent ragged cells read back as None, not "".
    assert cell_at(table, 0, 1) is None
    assert cell_at(table, 0, 2) is None


def test_jsonl_round_trip() -> None:
    tables = [
        from_grid("t1", "doc1", _GRID, page=3, caption="Табл. 1. Свойства."),
        from_grid("t2", "doc1", [["a", "b"], ["1", "2"]], page=4),
    ]
    restored = from_jsonl(to_jsonl(tables))
    assert restored == tables
    # A trailing newline must not create a phantom table (lossless).
    assert from_jsonl(to_jsonl(tables) + "\n") == tables
    # Each line is standalone valid JSON matching as_dict().
    lines = to_jsonl(tables).split("\n")
    assert len(lines) == 2
    for line, table in zip(lines, tables, strict=True):
        assert json.loads(line) == table.as_dict()


def test_empty_list_serializes_to_empty_string() -> None:
    assert to_jsonl([]) == ""
    assert from_jsonl("") == []
    # Whitespace-only input also yields no tables.
    assert from_jsonl("  \n\n  ") == []


def test_cell_as_dict_from_dict() -> None:
    cell = TableCell(row_index=2, col_index=1, text="медь")
    d = cell.as_dict()
    assert d == {"row_index": 2, "col_index": 1, "text": "медь"}
    assert TableCell.from_dict(d) == cell


def test_table_as_dict_from_dict() -> None:
    table = from_grid("t1", "doc1", _GRID, page=3, caption="Табл. 1")
    d = table.as_dict()
    assert set(d.keys()) == _TABLE_FIELDS
    # cells are plain dicts, not dataclass reprs.
    assert d["cells"][0] == {"row_index": 0, "col_index": 0, "text": "copper"}
    assert d["header"] == ["material", "твёрдость"]
    assert d["page"] == 3
    assert d["caption"] == "Табл. 1"
    # from_dict is the exact inverse of as_dict.
    assert TableExtract.from_dict(d) == table


def test_empty_grid() -> None:
    table = from_grid("t0", "doc1", [])
    assert table.n_rows == 0
    assert table.n_cols == 0
    assert table.header == []
    assert table.cells == []
    assert table.page is None
    assert table.caption is None
    # Round-trips cleanly through JSONL.
    assert from_jsonl(to_jsonl([table])) == [table]


def test_caption_preserved() -> None:
    table = from_grid("t1", "doc1", _GRID, caption="Рис. 2. Состав сплава")
    assert table.caption == "Рис. 2. Состав сплава"
    # Preserved across the dict + JSONL round-trip.
    assert TableExtract.from_dict(table.as_dict()).caption == "Рис. 2. Состав сплава"
    assert from_jsonl(to_jsonl([table]))[0].caption == "Рис. 2. Состав сплава"
    # Absent caption stays None (default).
    assert from_grid("t9", "doc1", _GRID).caption is None
