"""Dependency-free Excel export via SpreadsheetML 2003 XML (§22).

Экспорт в Excel без зависимостей: SpreadsheetML 2003 — a single-file, XML-based
``.xls`` workbook (the ``<?mso-application progid="Excel.Sheet"?>`` dialect that
Excel 2003+ opens natively). This is a **pure-stdlib** alternative to the
:mod:`openpyxl`-guarded XLSX path in :mod:`kg_common.tabular_export`: it works
even when the optional ``openpyxl`` dependency is absent, so callers always have
a spreadsheet backend available.

Only stdlib is used (:mod:`xml.sax.saxutils` for escaping). Cell rendering is
uniform: a column missing from a row (or present with ``None``) renders as an
empty ``String`` cell; numeric values (``int``/``float``, excluding ``bool``)
get ``ss:Type="Number"``; everything else is stringified and emitted as
``String`` with XML-escaped text — экранирование текста.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape, quoteattr

_MSO_PI = '<?mso-application progid="Excel.Sheet"?>'
_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>'


@dataclass(frozen=True)
class SheetData:
    """One worksheet: name, ordered columns and rows — данные листа (§22).

    ``rows`` is a tuple of tuples, each inner tuple aligned to ``columns`` by
    position. Frozen + hashable so sheets can be cached/compared.
    """

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view; ``rows`` stays a tuple of tuples — as-dict вид."""
        return {"name": self.name, "columns": self.columns, "rows": self.rows}


def _is_number(value: Any) -> bool:
    """True for real numerics (``int``/``float``) but not ``bool`` — число ли."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def build_sheet(name: str, rows: list[dict], columns: list[str]) -> SheetData:
    """Build a :class:`SheetData` from dict rows in ``columns`` order (§22).

    Each row dict is projected onto ``columns``; a missing key (or ``None``)
    becomes an empty string, matching the empty-``String``-cell rendering of
    :func:`to_spreadsheetml`.
    """
    cols = tuple(columns)
    built: list[tuple[Any, ...]] = []
    for row in rows:
        cells = tuple("" if row.get(col) is None else row.get(col) for col in cols)
        built.append(cells)
    return SheetData(name=name, columns=cols, rows=tuple(built))


def _cell_xml(value: Any) -> str:
    """Render one ``<Cell><Data>`` element with the right ``ss:Type`` (§22)."""
    if _is_number(value):
        return f'<Cell><Data ss:Type="Number">{escape(str(value))}</Data></Cell>'
    text = "" if value is None else str(value)
    return f'<Cell><Data ss:Type="String">{escape(text)}</Data></Cell>'


def _row_xml(cells: Sequence[Any]) -> str:
    """Render one ``<Row>`` element from a sequence of cell values — строка."""
    return "<Row>" + "".join(_cell_xml(c) for c in cells) + "</Row>"


def _worksheet_xml(sheet: SheetData) -> str:
    """Render one ``<Worksheet>`` with a header row first, then data (§22)."""
    header = _row_xml(sheet.columns)
    body = "".join(_row_xml(r) for r in sheet.rows)
    name_attr = quoteattr(sheet.name)
    return f"<Worksheet ss:Name={name_attr}><Table>{header}{body}</Table></Worksheet>"


def to_spreadsheetml(sheets: Sequence[SheetData]) -> str:
    """Serialise ``sheets`` to a SpreadsheetML 2003 workbook string (§22).

    The output starts with an XML declaration and the ``mso-application``
    processing instruction, then a ``<Workbook>`` holding one ``<Worksheet>``
    per sheet. Each worksheet emits its header row first, then data rows;
    numeric cells carry ``ss:Type="Number"``, all others ``String`` with
    XML-escaped text. Parseable by :mod:`xml.etree.ElementTree`.
    """
    ns = (
        'xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"'
    )
    worksheets = "".join(_worksheet_xml(s) for s in sheets)
    return f"{_XML_DECL}\n{_MSO_PI}\n<Workbook {ns}>{worksheets}</Workbook>"
