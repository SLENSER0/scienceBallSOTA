"""Tests for whole-table Markdown serialization (§5.9 / §5.7).

Hand-checked assertions on the pipe-table renderer and its inverse: shape of the
output (header + separator + one line per row), ragged-row padding, over-long
row truncation, pipe escaping, and an exact round-trip through
``parse_markdown``.
"""

from __future__ import annotations

from kg_extractors.table_markdown import MarkdownTable, parse_markdown, to_markdown


def test_basic_shape_three_lines_with_separator() -> None:
    """Header + ``---`` separator + one data line; counts match (§5.9)."""
    table = to_markdown(["a", "b"], [["1", "2"]])
    lines = table.markdown.splitlines()
    assert len(lines) == 3
    assert "---" in lines[1]
    assert table.n_cols == 2
    assert table.n_rows == 1


def test_ragged_row_is_padded_to_n_cols() -> None:
    """A row shorter than n_cols is padded so every data line has 2 cells."""
    table = to_markdown(["a", "b"], [["1"]])
    data_line = table.markdown.splitlines()[2]
    # Two interior separators => two cells (padded with '').
    assert data_line.count("|") == 3
    headers, rows = parse_markdown(table.markdown)
    assert headers == ["a", "b"]
    assert rows == [["1", ""]]


def test_over_long_row_truncated_to_n_cols() -> None:
    """A row longer than n_cols is truncated to n_cols columns."""
    table = to_markdown(["a", "b"], [["1", "2", "3", "4"]])
    assert table.n_cols == 2
    _, rows = parse_markdown(table.markdown)
    assert rows == [["1", "2"]]


def test_embedded_pipe_is_escaped() -> None:
    """A cell 'x|y' appears escaped as 'x\\|y' in the rendered markdown."""
    table = to_markdown(["a", "b"], [["x|y", "z"]])
    assert "x\\|y" in table.markdown
    # Round-trips back to the original unescaped value.
    _, rows = parse_markdown(table.markdown)
    assert rows == [["x|y", "z"]]


def test_round_trip_unaligned() -> None:
    """parse_markdown inverts an unaligned render exactly (round-trip)."""
    md = to_markdown(["a", "b"], [["1", "2"]], align=False).markdown
    assert parse_markdown(md) == (["a", "b"], [["1", "2"]])


def test_round_trip_aligned_multi_row() -> None:
    """Alignment padding is stripped on parse — round-trip holds when aligned."""
    headers = ["name", "value"]
    rows = [["alpha", "1"], ["b", "22"], ["gamma", "333"]]
    md = to_markdown(headers, rows, align=True).markdown
    assert parse_markdown(md) == (headers, rows)


def test_empty_rows_still_has_header_and_separator() -> None:
    """Empty rows list yields n_rows==0 but header + separator remain."""
    table = to_markdown(["a", "b"], [])
    lines = table.markdown.splitlines()
    assert table.n_rows == 0
    assert len(lines) == 2
    assert "---" in lines[1]
    assert parse_markdown(table.markdown) == (["a", "b"], [])


def test_as_dict_exposes_shape() -> None:
    """as_dict() carries the frozen fields including n_cols."""
    table = to_markdown(["a", "b"], [["1", "2"]])
    d = table.as_dict()
    assert d["n_cols"] == 2
    assert d["n_rows"] == 1
    assert d["markdown"] == table.markdown


def test_aligned_columns_have_equal_width() -> None:
    """With align=True each column is space-padded to a common width."""
    table = to_markdown(["a", "bb"], [["ccc", "d"]], align=True)
    lines = table.markdown.splitlines()
    # Every rendered line has identical length once columns are aligned.
    assert len({len(ln) for ln in lines}) == 1


def test_frozen_dataclass_is_immutable() -> None:
    """MarkdownTable is frozen — fields cannot be reassigned."""
    table = MarkdownTable(markdown="x", n_rows=0, n_cols=1)
    try:
        table.n_rows = 5  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("MarkdownTable should be frozen")
