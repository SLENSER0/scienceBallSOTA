"""Tests for SpreadsheetML 2003 XML export (§22) — hand-checkable assertions."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from kg_common.spreadsheetml_export import (
    SheetData,
    build_sheet,
    to_spreadsheetml,
)

_SS = "urn:schemas-microsoft-com:office:spreadsheet"


def test_header_and_prolog() -> None:
    sheet = build_sheet("S1", [{"a": 1, "b": "x"}], ["a", "b"])
    xml = to_spreadsheetml([sheet])
    assert xml.startswith("<?xml")
    assert '<?mso-application progid="Excel.Sheet"?>' in xml
    # Parses cleanly via ElementTree.
    ET.fromstring(xml)


def test_numeric_cell_type_and_data() -> None:
    sheet = build_sheet("Nums", [{"n": 5}], ["n"])
    xml = to_spreadsheetml([sheet])
    assert '<Data ss:Type="Number">5</Data>' in xml


def test_string_cell_type() -> None:
    sheet = build_sheet("Strs", [{"s": "hello"}], ["s"])
    xml = to_spreadsheetml([sheet])
    assert '<Data ss:Type="String">hello</Data>' in xml


def test_ampersand_escaped() -> None:
    sheet = build_sheet("Amp", [{"s": "R&D"}], ["s"])
    xml = to_spreadsheetml([sheet])
    assert "R&amp;D" in xml
    assert "R&D" not in xml
    # Still parseable after escaping.
    ET.fromstring(xml)


def test_two_sheets_two_worksheets() -> None:
    s1 = build_sheet("One", [{"a": 1}], ["a"])
    s2 = build_sheet("Two", [{"a": 2}], ["a"])
    xml = to_spreadsheetml([s1, s2])
    root = ET.fromstring(xml)
    worksheets = root.findall(f"{{{_SS}}}Worksheet")
    assert len(worksheets) == 2
    names = [w.get(f"{{{_SS}}}Name") for w in worksheets]
    assert names == ["One", "Two"]


def test_header_row_emitted_first() -> None:
    sheet = build_sheet("H", [{"a": 9, "b": 8}], ["a", "b"])
    xml = to_spreadsheetml([sheet])
    root = ET.fromstring(xml)
    table = root.find(f"{{{_SS}}}Worksheet/{{{_SS}}}Table")
    rows = table.findall(f"{{{_SS}}}Row")
    first_cells = [c.find(f"{{{_SS}}}Data").text for c in rows[0].findall(f"{{{_SS}}}Cell")]
    assert first_cells == ["a", "b"]
    second_cells = [c.find(f"{{{_SS}}}Data").text for c in rows[1].findall(f"{{{_SS}}}Cell")]
    assert second_cells == ["9", "8"]


def test_missing_key_empty_string_cell() -> None:
    sheet = build_sheet("M", [{"a": 1}], ["a", "b"])
    xml = to_spreadsheetml([sheet])
    root = ET.fromstring(xml)
    table = root.find(f"{{{_SS}}}Worksheet/{{{_SS}}}Table")
    data_row = table.findall(f"{{{_SS}}}Row")[1]
    cells = data_row.findall(f"{{{_SS}}}Cell")
    b_data = cells[1].find(f"{{{_SS}}}Data")
    assert b_data.get(f"{{{_SS}}}Type") == "String"
    assert (b_data.text or "") == ""


def test_as_dict_rows_tuple_of_tuples() -> None:
    sheet = build_sheet("D", [{"a": 1, "b": 2}], ["a", "b"])
    d = sheet.as_dict()
    assert isinstance(d["rows"], tuple)
    assert all(isinstance(r, tuple) for r in d["rows"])
    assert d["rows"] == ((1, 2),)
    assert d["columns"] == ("a", "b")
    assert d["name"] == "D"


def test_sheetdata_frozen_hashable() -> None:
    sheet = SheetData(name="X", columns=("a",), rows=((1,),))
    assert hash(sheet) is not None


def test_float_is_number_bool_is_string() -> None:
    sheet = build_sheet("T", [{"f": 1.5, "flag": True}], ["f", "flag"])
    xml = to_spreadsheetml([sheet])
    assert '<Data ss:Type="Number">1.5</Data>' in xml
    # bool must NOT be treated as a number.
    assert '<Data ss:Type="String">True</Data>' in xml
