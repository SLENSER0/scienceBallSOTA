"""Tests for per-cell source count + confidence banding (§24.13)."""

from __future__ import annotations

from kg_retrievers.comparison_cell_confidence import (
    CellConfidence,
    score_cell,
    score_table,
)


def test_four_distinct_sources_is_high() -> None:
    """(1) evidence a,b,c,d → source_count 4, confidence 'high', gap False."""
    cell = score_cell("gpu", "vram", ["a", "b", "c", "d"])
    assert cell.source_count == 4
    assert cell.confidence == "high"
    assert cell.gap is False


def test_no_evidence_is_gap_none() -> None:
    """(2) empty evidence → gap True, confidence 'none', source_count 0."""
    cell = score_cell("gpu", "price", [])
    assert cell.gap is True
    assert cell.confidence == "none"
    assert cell.source_count == 0


def test_duplicate_ids_collapse() -> None:
    """(3) duplicate ids a,a → source_count 1, confidence 'low'."""
    cell = score_cell("gpu", "vram", ["a", "a"])
    assert cell.source_count == 1
    assert cell.confidence == "low"
    assert cell.gap is False


def test_two_sources_is_medium() -> None:
    """(4) 2 distinct ids → confidence 'medium'."""
    cell = score_cell("gpu", "vram", ["a", "b"])
    assert cell.source_count == 2
    assert cell.confidence == "medium"


def test_three_sources_is_medium_boundary() -> None:
    """Band boundary: 3 distinct ids → 'medium', 4 crosses into 'high'."""
    assert score_cell("r", "c", ["a", "b", "c"]).confidence == "medium"
    assert score_cell("r", "c", ["a", "b", "c", "d"]).confidence == "high"


def test_score_table_sorts_by_row_then_col() -> None:
    """(5) score_table returns cells sorted by (row, col)."""
    cells: dict[tuple[str, str], list[str]] = {
        ("b", "y"): ["1"],
        ("a", "z"): ["1", "2"],
        ("a", "y"): ["1", "2", "3", "4"],
        ("b", "x"): [],
    }
    scored = score_table(cells)
    keys = [(c.row, c.col) for c in scored]
    assert keys == [("a", "y"), ("a", "z"), ("b", "x"), ("b", "y")]


def test_as_dict_gap_is_bool() -> None:
    """(6) as_dict()['gap'] is a real bool, JSON-safe."""
    d = score_cell("gpu", "price", []).as_dict()
    assert d["gap"] is True
    assert isinstance(d["gap"], bool)
    backed = score_cell("gpu", "vram", ["a"]).as_dict()
    assert backed["gap"] is False
    assert isinstance(backed["gap"], bool)


def test_gap_cell_still_reported() -> None:
    """(7) a table with a gap cell still reports that cell (not dropped)."""
    cells: dict[tuple[str, str], list[str]] = {
        ("gpu", "vram"): ["a", "b"],
        ("gpu", "price"): [],
    }
    scored = score_table(cells)
    assert len(scored) == 2
    gap_cells = [c for c in scored if c.gap]
    assert len(gap_cells) == 1
    assert (gap_cells[0].row, gap_cells[0].col) == ("gpu", "price")
    assert gap_cells[0].confidence == "none"


def test_frozen_and_full_as_dict() -> None:
    """CellConfidence is frozen and as_dict round-trips all fields."""
    cell = score_cell("gpu", "vram", ["a", "b", "c"])
    assert isinstance(cell, CellConfidence)
    try:
        cell.source_count = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("CellConfidence should be frozen")
    assert cell.as_dict() == {
        "row": "gpu",
        "col": "vram",
        "source_count": 3,
        "confidence": "medium",
        "gap": False,
    }
