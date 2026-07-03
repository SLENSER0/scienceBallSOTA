"""Comparison-table export to CSV / Markdown / XLSX (§24.16)."""

from __future__ import annotations

import csv
import io
import sys

import pytest

from kg_common.tabular_export import (
    ComparisonExport,
    ExportUnavailable,
    rows_to_markdown_table,
    to_csv,
    to_xlsx,
)

# Small fixed comparison table — сравнение металлов (name / value + one gap).
COLUMNS = ["name", "value", "unit"]
ROWS = [
    {"name": "медь", "value": 8.96, "unit": "г/см³"},
    {"name": "железо", "value": 7.87},  # "unit" intentionally missing
]


def test_csv_has_header_plus_n_rows() -> None:
    lines = to_csv(ROWS, COLUMNS).splitlines()
    assert lines[0] == "name,value,unit"  # header is exactly the columns
    assert len(lines) == 1 + len(ROWS)  # header + one line per row
    # Parsing it back yields the same records (column order preserved).
    parsed = list(csv.reader(io.StringIO(to_csv(ROWS, COLUMNS))))
    assert parsed[0] == COLUMNS
    assert parsed[1] == ["медь", "8.96", "г/см³"]


def test_csv_escapes_commas_and_quotes() -> None:
    rows = [{"name": 'a,b "c"', "value": "plain"}]
    out = to_csv(rows, ["name", "value"])
    # RFC-4180: a field with a comma or quote is wrapped in quotes; inner
    # quotes are doubled. So a,b "c"  ->  "a,b ""c"""
    assert out.splitlines()[1] == '"a,b ""c""",plain'
    # And it round-trips back to the original cell value via csv.reader.
    back = list(csv.reader(io.StringIO(out)))[1]
    assert back == ['a,b "c"', "plain"]


def test_csv_keeps_ru_chars() -> None:
    out = to_csv([{"name": "плотность"}], ["name"])
    assert "плотность" in out
    assert out.splitlines() == ["name", "плотность"]


def test_csv_missing_key_is_empty_cell() -> None:
    # Second row has no "unit" key -> trailing empty cell, no crash.
    row = to_csv(ROWS, COLUMNS).splitlines()[2]
    assert row == "железо,7.87,"
    # None values render the same way as a missing key.
    assert to_csv([{"name": None, "value": 1}], ["name", "value"]).splitlines()[1] == ",1"


def test_empty_rows_gives_header_only() -> None:
    assert to_csv([], COLUMNS).splitlines() == ["name,value,unit"]
    md = rows_to_markdown_table([], COLUMNS)
    assert md.split("\n") == ["| name | value | unit |", "| --- | --- | --- |"]


def test_markdown_table_shape() -> None:
    md = rows_to_markdown_table(ROWS, COLUMNS)
    lines = md.split("\n")
    assert len(lines) == 2 + len(ROWS)  # header + separator + N rows
    assert lines[0] == "| name | value | unit |"
    assert lines[1] == "| --- | --- | --- |"  # GitHub separator row
    assert lines[2] == "| медь | 8.96 | г/см³ |"
    assert lines[3] == "| железо | 7.87 |  |"  # missing "unit" -> empty cell


def test_markdown_escapes_pipe_and_newline() -> None:
    rows = [{"c": "a|b\nc"}]
    line = rows_to_markdown_table(rows, ["c"]).split("\n")[2]
    # Raw "|" is escaped and the newline is flattened to a space.
    assert line == r"| a\|b c |"


def test_xlsx_writes_file_with_header_first_row(tmp_path) -> None:
    openpyxl = pytest.importorskip("openpyxl")  # skips cleanly if absent
    path = tmp_path / "cmp.xlsx"
    returned = to_xlsx(ROWS, COLUMNS, path)
    assert returned == path
    assert path.exists()
    wb = openpyxl.load_workbook(str(path))
    ws = wb.active
    assert [c.value for c in ws[1]] == COLUMNS  # first row == columns
    # Data rows land in order, with the missing "unit" cell empty.
    assert [c.value for c in ws[2]] == ["медь", "8.96", "г/см³"]
    # The written empty-string cell reads back as None (openpyxl normalises
    # empty cells) — the missing "unit" key produced an empty trailing cell.
    assert [c.value for c in ws[3]] == ["железо", "7.87", None]


def test_to_xlsx_raises_when_openpyxl_absent(tmp_path, monkeypatch) -> None:
    # Force `import openpyxl` to fail (None in sys.modules -> ImportError).
    monkeypatch.setitem(sys.modules, "openpyxl", None)
    with pytest.raises(ExportUnavailable, match="openpyxl not installed"):
        to_xlsx(ROWS, COLUMNS, tmp_path / "x.xlsx")


def test_comparison_export_helper_roundtrips() -> None:
    exp = ComparisonExport(columns=COLUMNS, rows=ROWS)
    assert exp.to_csv() == to_csv(ROWS, COLUMNS)
    assert exp.to_markdown() == rows_to_markdown_table(ROWS, COLUMNS)
    d = exp.as_dict()
    assert d["columns"] == COLUMNS
    assert d["rows"][0]["name"] == "медь"
