"""Table-row linearizer tests — ``table_row`` chunks with header context (§5.9).

Hand-checked expectations over RU + EN table data: ``linearize_row`` embeds
column headers, skips empty cells, and joins with ``'; '``; ``rows_to_chunks``
assigns ``row_index`` from 0, pads ragged rows so every header key survives, and
yields ``[]`` for an empty table; ``RowChunk.as_dict`` carries the §8.3 anchors.
"""

from __future__ import annotations

from kg_extractors.table_row_chunker import RowChunk, linearize_row, rows_to_chunks


def test_linearize_row_ru_embeds_headers() -> None:
    assert linearize_row(["материал", "твёрдость"], ["Ti", "350"]) == "материал=Ti; твёрдость=350"


def test_linearize_row_skips_empty_cell() -> None:
    assert linearize_row(["a", "b"], ["1", ""]) == "a=1"


def test_linearize_row_skips_whitespace_only_cell() -> None:
    assert linearize_row(["a", "b"], ["1", "   "]) == "a=1"


def test_linearize_row_strips_cell_whitespace() -> None:
    assert linearize_row(["a"], ["  Ti  "]) == "a=Ti"


def test_rows_to_chunks_assigns_row_index_from_zero() -> None:
    chunks = rows_to_chunks("t1", ["a", "b"], [["1", "2"], ["3", "4"]])
    assert [c.row_index for c in chunks] == [0, 1]


def test_each_chunk_text_contains_a_header_name() -> None:
    headers = ["материал", "твёрдость"]
    chunks = rows_to_chunks("t1", headers, [["Ti", "350"], ["Al", "120"]])
    for chunk in chunks:
        assert any(h in chunk.text for h in headers)


def test_ragged_row_is_padded_with_all_header_keys() -> None:
    chunks = rows_to_chunks("t1", ["a", "b", "c"], [["1"]])
    assert set(chunks[0].cells) == {"a", "b", "c"}
    assert chunks[0].cells["b"] == ""
    assert chunks[0].cells["c"] == ""
    # Only the non-empty cell survives into the linearized text.
    assert chunks[0].text == "a=1"


def test_row_longer_than_headers_is_truncated() -> None:
    chunks = rows_to_chunks("t1", ["a", "b"], [["1", "2", "3"]])
    assert set(chunks[0].cells) == {"a", "b"}
    assert chunks[0].text == "a=1; b=2"


def test_as_dict_carries_anchors_and_page() -> None:
    chunk = rows_to_chunks("tbl-42", ["a"], [["1"]], page=7)[0]
    d = chunk.as_dict()
    assert d["table_id"] == "tbl-42"
    assert d["row_index"] == 0
    assert d["page"] == 7
    assert d["cells"] == {"a": "1"}


def test_as_dict_cells_is_a_copy() -> None:
    chunk = RowChunk("t1", 0, "a=1", {"a": "1"}, None)
    d = chunk.as_dict()
    d["cells"]["a"] = "mutated"
    assert chunk.cells["a"] == "1"


def test_empty_rows_yields_empty_list() -> None:
    assert rows_to_chunks("t1", ["a", "b"], []) == []


def test_default_page_is_none() -> None:
    chunk = rows_to_chunks("t1", ["a"], [["1"]])[0]
    assert chunk.page is None
