"""Тесты CSV-экспорта подграфа (§14.15).

Tests for the §14.15 subgraph CSV serializer: header ordering, RFC 4180 quoting
(commas, embedded double-quotes), missing-column empty cells, row counts, the
guaranteed ``source``/``target`` edge columns and the frozen wire form.
"""

from __future__ import annotations

from api_gateway.subgraph_csv_export import (
    CsvExport,
    export_edges_csv,
    export_nodes_csv,
)


def test_header_equals_joined_columns() -> None:
    """(1) первая строка == ','.join(columns)."""
    columns = ["id", "label", "type"]
    out = export_nodes_csv([], columns)
    header = out.splitlines()[0]
    assert header == ",".join(columns)


def test_value_with_comma_is_quoted() -> None:
    """(2) значение с запятой оборачивается в двойные кавычки."""
    nodes = [{"id": "n1", "label": "Smith, John"}]
    out = export_nodes_csv(nodes, ["id", "label"])
    data_line = out.splitlines()[1]
    assert '"Smith, John"' in data_line


def test_missing_column_yields_empty_field() -> None:
    """(3) отсутствующий ключ → пустая ячейка (два соседних разделителя)."""
    nodes = [{"id": "n1", "type": "Person"}]
    out = export_nodes_csv(nodes, ["id", "label", "type"])
    data_line = out.splitlines()[1]
    assert data_line == "n1,,Person"
    assert ",," in data_line


def test_row_count_matches_nodes_plus_header() -> None:
    """(4) число строк == len(nodes)+1 с учётом хвостового перевода строки."""
    nodes = [{"id": f"n{i}"} for i in range(3)]
    out = export_nodes_csv(nodes, ["id"])
    assert out.endswith("\n")
    lines = out.splitlines()
    assert len(lines) == len(nodes) + 1


def test_edges_include_source_target_in_order() -> None:
    """(5) export_edges_csv гарантирует колонки source/target в порядке."""
    edges = [{"source": "a", "target": "b", "rel": "cites"}]
    out = export_edges_csv(edges, ["rel"])
    header = out.splitlines()[0].split(",")
    assert header[0] == "source"
    assert header[1] == "target"
    assert header.index("source") < header.index("target") < header.index("rel")
    data = out.splitlines()[1].split(",")
    assert data[0] == "a"
    assert data[1] == "b"
    assert data[2] == "cites"


def test_embedded_double_quote_is_doubled() -> None:
    """(6) встроенная кавычка удваивается по правилам CSV-экранирования."""
    nodes = [{"id": "n1", "label": 'the "best" node'}]
    out = export_nodes_csv(nodes, ["id", "label"])
    data_line = out.splitlines()[1]
    assert '"the ""best"" node"' in data_line


def test_csvexport_as_dict_keys() -> None:
    """(7) CsvExport.as_dict() возвращает {'nodes_csv','edges_csv'}."""
    exp = CsvExport(nodes_csv="id\nn1\n", edges_csv="source,target\na,b\n")
    d = exp.as_dict()
    assert set(d) == {"nodes_csv", "edges_csv"}
    assert d["nodes_csv"] == "id\nn1\n"
    assert d["edges_csv"] == "source,target\na,b\n"


def test_empty_nodes_yields_only_header() -> None:
    """(8) пустой список узлов → только строка заголовка."""
    columns = ["id", "label"]
    out = export_nodes_csv([], columns)
    assert out == ",".join(columns) + "\n"
    assert len(out.splitlines()) == 1


def test_csvexport_is_frozen() -> None:
    """CsvExport неизменяем (frozen dataclass)."""
    exp = CsvExport(nodes_csv="", edges_csv="")
    try:
        exp.nodes_csv = "x"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("CsvExport must be frozen")


def test_newline_in_value_is_quoted() -> None:
    """Значение с переводом строки экранируется кавычками (RFC 4180)."""
    nodes = [{"id": "n1", "label": "line1\nline2"}]
    out = export_nodes_csv(nodes, ["id", "label"])
    assert '"line1\nline2"' in out
