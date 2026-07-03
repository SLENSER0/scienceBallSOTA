"""Tests for cross-page table stitching (§5.7).

Hand-checkable assertions over :func:`stitch_tables` and :class:`StitchedTable`.
"""

from __future__ import annotations

from kg_extractors.table_stitch import StitchedTable, stitch_tables


def _table(headers: list[str], rows: list[list[str]], page: int) -> dict:
    return {"headers": headers, "rows": rows, "page": page}


def test_same_headers_merge_across_pages():
    # Two fragments with identical ['M','HV'] headers on pages 3 and 4 stitch.
    t1 = _table(["M", "HV"], [["Al", "35"]], 3)
    t2 = _table(["M", "HV"], [["Cu", "120"]], 4)
    result = stitch_tables([t1, t2])
    assert len(result) == 1
    merged = result[0]
    assert isinstance(merged, StitchedTable)
    assert merged.source_count == 2
    assert merged.page_start == 3
    assert merged.page_end == 4
    # Rows are the concatenation, order preserved.
    assert merged.rows == (("Al", "35"), ("Cu", "120"))


def test_different_headers_stay_separate():
    t1 = _table(["M", "HV"], [["Al", "35"]], 3)
    t2 = _table(["Element", "Fraction"], [["Cu", "0.1"]], 4)
    result = stitch_tables([t1, t2])
    assert len(result) == 2
    assert result[0].source_count == 1
    assert result[1].source_count == 1


def test_header_match_is_case_and_space_insensitive():
    # 'M ' vs 'm' and 'HV' vs 'hv ' normalize to the same key.
    t1 = _table(["M ", "HV"], [["Al", "35"]], 1)
    t2 = _table(["m", "hv "], [["Cu", "120"]], 2)
    result = stitch_tables([t1, t2])
    assert len(result) == 1
    assert result[0].source_count == 2


def test_row_order_preserved_across_merge():
    t1 = _table(["A"], [["1"], ["2"]], 1)
    t2 = _table(["A"], [["3"], ["4"]], 2)
    result = stitch_tables([t1, t2])
    assert result[0].rows == (("1",), ("2",), ("3",), ("4",))


def test_single_table_yields_one_with_equal_page_bounds():
    result = stitch_tables([_table(["M", "HV"], [["Al", "35"]], 7)])
    assert len(result) == 1
    assert result[0].page_start == result[0].page_end == 7
    assert result[0].source_count == 1


def test_empty_input_yields_empty_list():
    assert stitch_tables([]) == []


def test_as_dict_shape_for_merged_case():
    t1 = _table(["M", "HV"], [["Al", "35"]], 3)
    t2 = _table(["M", "HV"], [["Cu", "120"]], 4)
    d = stitch_tables([t1, t2])[0].as_dict()
    assert d["rows"] == [["Al", "35"], ["Cu", "120"]]
    assert all(isinstance(row, list) for row in d["rows"])
    assert isinstance(d["rows"], list)
    assert d["source_count"] == 2
    assert d["headers"] == ["M", "HV"]
    assert d["page_start"] == 3
    assert d["page_end"] == 4


def test_non_adjacent_same_headers_do_not_merge():
    # A differing header between two matching ones breaks the run into 3 groups.
    t1 = _table(["A"], [["1"]], 1)
    t2 = _table(["B"], [["2"]], 2)
    t3 = _table(["A"], [["3"]], 3)
    result = stitch_tables([t1, t2, t3])
    assert [r.source_count for r in result] == [1, 1, 1]


def test_unsorted_input_is_ordered_by_page():
    t_late = _table(["M", "HV"], [["Cu", "120"]], 4)
    t_early = _table(["M", "HV"], [["Al", "35"]], 3)
    result = stitch_tables([t_late, t_early])
    assert len(result) == 1
    assert result[0].rows == (("Al", "35"), ("Cu", "120"))
    assert result[0].page_start == 3
    assert result[0].page_end == 4
