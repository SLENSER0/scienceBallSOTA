"""Hand-checkable tests for §17.9 large-graph minimap density-grid payload."""

from __future__ import annotations

from kg_retrievers.graph_minimap import (
    MinimapCell,
    MinimapPayload,
    build_minimap,
)


def test_single_node_one_cell() -> None:
    """Assertion (1): один узел в (0,0) -> одна ячейка count==1, density==1.0, max_count==1."""
    payload = build_minimap([{"x": 0.0, "y": 0.0}])
    assert isinstance(payload, MinimapPayload)
    assert payload.max_count == 1
    assert len(payload.cells) == 1
    cell = payload.cells[0]
    assert isinstance(cell, MinimapCell)
    assert cell.count == 1
    assert cell.density == 1.0


def test_two_nodes_same_cell() -> None:
    """Assertion (2): два узла в одной точке -> ячейка count==2."""
    payload = build_minimap([{"x": 5.0, "y": 5.0}, {"x": 5.0, "y": 5.0}])
    assert len(payload.cells) == 1
    assert payload.cells[0].count == 2
    assert payload.max_count == 2


def test_bounds_from_min_max() -> None:
    """Assertion (3): границы для узлов (0,0),(10,20) == (0.0,0.0,10.0,20.0)."""
    payload = build_minimap([{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 20.0}])
    assert payload.bounds == (0.0, 0.0, 10.0, 20.0)


def test_node_at_max_corner_lands_in_last_cell() -> None:
    """Assertion (4): узел ровно в углу (10,20) -> col==cols-1, row==rows-1."""
    payload = build_minimap([{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 20.0}], cols=16, rows=16)
    corner = {(c.col, c.row) for c in payload.cells}
    assert (payload.cols - 1, payload.rows - 1) in corner


def test_empty_nodes() -> None:
    """Assertion (5): пустой список -> max_count==0 и cells==()."""
    payload = build_minimap([])
    assert payload.max_count == 0
    assert payload.cells == ()


def test_cols_four_x_extremes() -> None:
    """Assertion (6): cols=4, узлы x=0 и x=10 (miny==maxy) -> колонки 0 и 3."""
    payload = build_minimap([{"x": 0.0, "y": 7.0}, {"x": 10.0, "y": 7.0}], cols=4, rows=4)
    cols_used = sorted(c.col for c in payload.cells)
    assert cols_used == [0, 3]


def test_as_dict_bounds() -> None:
    """Assertion (7): as_dict()['bounds'] использует именованные углы."""
    payload = build_minimap([{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 20.0}])
    assert payload.as_dict()["bounds"] == {
        "minX": 0.0,
        "minY": 0.0,
        "maxX": 10.0,
        "maxY": 20.0,
    }


def test_cells_sorted_by_row_col() -> None:
    """Ячейки отсортированы по (row, col) — детерминированный payload (§17.9)."""
    payload = build_minimap(
        [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 0.0, "y": 10.0},
        ],
        cols=4,
        rows=4,
    )
    keys = [(c.row, c.col) for c in payload.cells]
    assert keys == sorted(keys)


def test_as_dict_cells_are_dicts() -> None:
    """as_dict() отдаёт cells как список плоских dict (§17.9)."""
    payload = build_minimap([{"x": 0.0, "y": 0.0}])
    cells = payload.as_dict()["cells"]
    assert cells == [{"col": 0, "row": 0, "count": 1, "density": 1.0}]
