"""Row/dict -> CSV serialisation tests — экспорт строк в CSV (§22.5)."""

from __future__ import annotations

import csv
import io

from kg_common.csv_export import dicts_to_csv, infer_columns, rows_to_csv

# Small fixed table — сравнение металлов (name / value + one gap).
COLUMNS = ["name", "value", "unit"]
ROWS = [
    {"name": "медь", "value": 8.96, "unit": "г/см³"},
    {"name": "железо", "value": 7.87},  # "unit" intentionally missing
]


def test_header_plus_n_rows() -> None:
    lines = rows_to_csv(ROWS, COLUMNS).splitlines()
    assert lines[0] == "name,value,unit"  # header is exactly the columns
    assert len(lines) == 1 + len(ROWS)  # header + one line per row
    # Parsing it back yields the same records (column order preserved).
    parsed = list(csv.reader(io.StringIO(rows_to_csv(ROWS, COLUMNS))))
    assert parsed[0] == COLUMNS
    assert parsed[1] == ["медь", "8.96", "г/см³"]


def test_dicts_to_csv_infers_columns() -> None:
    # Columns are the first-seen union of keys: name, value (from row 0), unit
    # never appears because no row here has it.
    out = dicts_to_csv([{"name": "медь", "value": 1}, {"value": 2, "name": "цинк"}])
    lines = out.splitlines()
    assert lines[0] == "name,value"  # first-seen order, not sorted
    assert lines[1] == "медь,1"
    assert lines[2] == "цинк,2"  # second row's keys reordered to columns


def test_infer_columns_first_seen_stable() -> None:
    # A key first seen only in a later row is appended, not sorted in.
    cols = infer_columns([{"b": 1, "a": 2}, {"a": 3, "c": 4}])
    assert cols == ["b", "a", "c"]  # b,a from row0; c appended from row1


def test_escapes_commas_and_quotes() -> None:
    rows = [{"name": 'a,b "c"', "value": "plain"}]
    out = rows_to_csv(rows, ["name", "value"])
    # RFC-4180: a field with a comma or quote is wrapped in quotes; inner
    # quotes are doubled. So a,b "c"  ->  "a,b ""c"""
    assert out.splitlines()[1] == '"a,b ""c""",plain'
    # And it round-trips back to the original cell value via csv.reader.
    back = list(csv.reader(io.StringIO(out)))[1]
    assert back == ['a,b "c"', "plain"]


def test_escapes_embedded_newline() -> None:
    # A newline inside a cell is quoted, not treated as a row break.
    out = rows_to_csv([{"c": "a\nb"}], ["c"])
    assert out == 'c\n"a\nb"\n'
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed == [["c"], ["a\nb"]]  # exactly two records, one cell each


def test_keeps_ru_chars() -> None:
    out = rows_to_csv([{"name": "плотность"}], ["name"])
    assert "плотность" in out
    assert out.splitlines() == ["name", "плотность"]


def test_missing_key_is_empty_cell() -> None:
    # Second row has no "unit" key -> trailing empty cell, no crash.
    row = rows_to_csv(ROWS, COLUMNS).splitlines()[2]
    assert row == "железо,7.87,"
    # None values render the same way as a missing key.
    assert rows_to_csv([{"name": None, "value": 1}], ["name", "value"]).splitlines()[1] == ",1"


def test_empty_input_gives_empty_string() -> None:
    # No rows and no columns -> "" (nothing to infer a header from).
    assert rows_to_csv([]) == ""
    assert dicts_to_csv([]) == ""
    # But explicit columns with no rows -> header line only.
    assert rows_to_csv([], COLUMNS).splitlines() == ["name,value,unit"]


def test_stable_column_order_across_rows() -> None:
    # Header order follows explicit `columns`, independent of per-dict key order.
    rows = [{"value": 1, "name": "a"}, {"name": "b", "value": 2}]
    lines = rows_to_csv(rows, ["name", "value"]).splitlines()
    assert lines == ["name,value", "a,1", "b,2"]
