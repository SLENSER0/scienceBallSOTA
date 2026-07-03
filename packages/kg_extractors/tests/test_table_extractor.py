"""Table extraction from markdown / TSV → structured rows (§5.7)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.table_extractor import (
    ParsedTable,
    extract_tables,
    parse_delimited,
    parse_markdown_table,
)


def test_markdown_three_col_two_rows() -> None:
    text = (
        "| material | hardness | limit |\n"
        "| --- | --- | --- |\n"
        "| steel | 200 | 500 |\n"
        "| copper | 100 | 210 |\n"
    )
    table = parse_markdown_table(text)
    assert table is not None
    assert table.headers == ["material", "hardness", "limit"]
    assert table.n_cols == 3
    assert table.n_rows == 2
    assert table.rows[0] == {"material": "steel", "hardness": "200", "limit": "500"}
    assert table.rows[1] == {"material": "copper", "hardness": "100", "limit": "210"}


def test_cell_at_correct() -> None:
    text = "| a | b |\n| --- | --- |\n| x1 | y1 |\n| x2 | y2 |\n"
    table = parse_markdown_table(text)
    assert table is not None
    assert table.cell_at(0, 0) == "x1"
    assert table.cell_at(0, 1) == "y1"
    assert table.cell_at(1, 0) == "x2"
    assert table.cell_at(1, 1) == "y2"
    with pytest.raises(IndexError):
        table.cell_at(2, 0)
    with pytest.raises(IndexError):
        table.cell_at(0, 2)


def test_tsv_parse() -> None:
    text = "alloy\tlimit\tphase\nAl\t120\talpha\nCu\t210\tbeta\n"
    table = parse_delimited(text)
    assert table is not None
    assert table.headers == ["alloy", "limit", "phase"]
    assert table.n_rows == 2
    assert table.rows[0] == {"alloy": "Al", "limit": "120", "phase": "alpha"}
    assert table.cell_at(1, 2) == "beta"


def test_multispace_aligned_parse() -> None:
    text = "alloy     limit     phase\nAl        120       alpha\nCu        210       beta\n"
    table = parse_delimited(text)
    assert table is not None
    assert table.headers == ["alloy", "limit", "phase"]
    assert table.rows[0] == {"alloy": "Al", "limit": "120", "phase": "alpha"}


def test_ragged_row_is_padded() -> None:
    # Second data row has only two cells → third column padded with "".
    text = "a\tb\tc\n1\t2\t3\n4\t5\n"
    table = parse_delimited(text)
    assert table is not None
    assert table.n_cols == 3
    assert table.rows[1] == {"a": "4", "b": "5", "c": ""}
    assert table.cell_at(1, 2) == ""


def test_empty_cells_preserved() -> None:
    text = "| a | b | c |\n| --- | --- | --- |\n| 1 |  | 3 |\n"
    table = parse_markdown_table(text)
    assert table is not None
    assert table.rows[0] == {"a": "1", "b": "", "c": "3"}


def test_russian_headers() -> None:
    text = "| материал | твёрдость | предел |\n| --- | --- | --- |\n| сталь | 200 HB | 500 МПа |\n"
    table = parse_markdown_table(text)
    assert table is not None
    assert table.headers == ["материал", "твёрдость", "предел"]
    assert table.rows[0]["твёрдость"] == "200 HB"
    assert table.cell_at(0, 2) == "500 МПа"


def test_no_table_text_returns_empty() -> None:
    prose = "Это обычный абзац без таблиц. Он состоит из двух предложений.\nВторая строка."
    assert extract_tables(prose) == []
    assert parse_markdown_table(prose) is None
    assert parse_delimited(prose) is None


def test_multiple_tables_in_one_block() -> None:
    text = (
        "Таблица 1:\n"
        "| материал | твёрдость |\n"
        "| --- | --- |\n"
        "| сталь | 200 |\n"
        "\n"
        "Таблица 2:\n"
        "сплав\tпредел\n"
        "Al\t120\n"
        "Cu\t210\n"
    )
    tables = extract_tables(text)
    assert len(tables) == 2
    assert tables[0].headers == ["материал", "твёрдость"]
    assert tables[0].n_rows == 1
    assert tables[1].headers == ["сплав", "предел"]
    assert tables[1].n_rows == 2
    # each span slices back to its own table text
    for tbl in tables:
        chunk = text[tbl.span[0] : tbl.span[1]]
        assert tbl.headers[0] in chunk


def test_header_only_table_zero_rows() -> None:
    text = "| a | b | c |\n| --- | --- | --- |\n"
    table = parse_markdown_table(text)
    assert table is not None
    assert table.n_cols == 3
    assert table.n_rows == 0
    assert table.rows == []


def test_as_dict_roundtrip_and_frozen() -> None:
    text = "| k | v |\n| --- | --- |\n| ключ | значение |\n"
    table = parse_markdown_table(text)
    assert table is not None
    d = table.as_dict()
    assert d["headers"] == ["k", "v"]
    assert d["rows"] == [{"k": "ключ", "v": "значение"}]
    assert d["n_rows"] == 1 and d["n_cols"] == 2
    # frozen dataclass: attributes cannot be reassigned
    with pytest.raises(FrozenInstanceError):
        table.headers = ["x"]  # type: ignore[misc]
    assert isinstance(table, ParsedTable)
