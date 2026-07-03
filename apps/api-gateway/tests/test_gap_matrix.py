"""Тесты построителя матрицы покрытия ``GET /gaps/matrix`` (§5.2.7).

Hand-checkable tests for :mod:`api_gateway.gap_matrix`: dense cell counting,
zero-row gaps, the ``min_count`` threshold, sparse gap-only projection, and the
``as_dict`` wire forms of both frozen dataclasses.
"""

from __future__ import annotations

from api_gateway.gap_matrix import (
    CoverageMatrix,
    MatrixCell,
    build_matrix,
    to_sparse,
)


def test_single_row_cell_counted_not_a_gap() -> None:
    """Одна строка → count==1, gap False / one row is covered (§5.2.7)."""
    m = build_matrix([{"material_id": "M", "property": "P"}], ["M"], ["P"])
    assert len(m.cells) == 1
    cell = m.cells[0]
    assert cell.material_id == "M"
    assert cell.property == "P"
    assert cell.count == 1
    assert cell.gap is False


def test_zero_rows_pair_is_gap() -> None:
    """Пара без строк → count==0, gap True / empty pair is a gap (§5.2.7)."""
    m = build_matrix([], ["M"], ["P"])
    assert len(m.cells) == 1
    assert m.cells[0].count == 0
    assert m.cells[0].gap is True


def test_dense_grid_size() -> None:
    """Плотная сетка = |materials| * |properties| / dense grid (§5.2.7)."""
    materials = ["M1", "M2", "M3"]
    properties = ["P1", "P2"]
    m = build_matrix([], materials, properties)
    assert len(m.cells) == len(materials) * len(properties)
    # Каждая пара присутствует ровно один раз / every pair exactly once.
    pairs = {(c.material_id, c.property) for c in m.cells}
    assert pairs == {(mat, prop) for mat in materials for prop in properties}


def test_min_count_threshold_makes_single_row_a_gap() -> None:
    """min_count=2 и одна строка → gap True / below threshold (§5.2.7)."""
    rows = [{"material_id": "M", "property": "P"}]
    m = build_matrix(rows, ["M"], ["P"], min_count=2)
    assert m.cells[0].count == 1
    assert m.cells[0].gap is True


def test_counts_accumulate_across_rows() -> None:
    """Несколько строк одной пары суммируются / counts accumulate (§5.2.7)."""
    rows = [
        {"material_id": "M", "property": "P"},
        {"material_id": "M", "property": "P"},
        {"material_id": "M", "property": "Q"},
    ]
    m = build_matrix(rows, ["M"], ["P", "Q"])
    by_pair = {(c.material_id, c.property): c for c in m.cells}
    assert by_pair[("M", "P")].count == 2
    assert by_pair[("M", "P")].gap is False
    assert by_pair[("M", "Q")].count == 1
    assert by_pair[("M", "Q")].gap is False


def test_to_sparse_returns_only_gap_cells() -> None:
    """to_sparse оставляет только пробелы / gap cells only (§5.2.7)."""
    rows = [{"material_id": "M1", "property": "P1"}]
    m = build_matrix(rows, ["M1", "M2"], ["P1"])
    sparse = to_sparse(m)
    assert sparse == [{"material_id": "M2", "property": "P1", "count": 0, "gap": True}]
    assert all(c["gap"] is True for c in sparse)


def test_axis_order_is_preserved() -> None:
    """Порядок осей сохраняется / material×property axis order (§5.2.7)."""
    m = build_matrix([], ["Mb", "Ma"], ["Pb", "Pa"])
    assert m.materials == ("Mb", "Ma")
    assert m.properties == ("Pb", "Pa")
    assert (m.cells[0].material_id, m.cells[0].property) == ("Mb", "Pb")
    assert (m.cells[1].material_id, m.cells[1].property) == ("Mb", "Pa")


def test_matrix_cell_as_dict() -> None:
    """MatrixCell.as_dict() отражает поля / cell wire form (§5.2.7)."""
    d = MatrixCell("M", "P", 0, True).as_dict()
    assert d["gap"] is True
    assert d == {"material_id": "M", "property": "P", "count": 0, "gap": True}


def test_coverage_matrix_as_dict_keys() -> None:
    """CoverageMatrix.as_dict() имеет нужные ключи / wire form keys (§5.2.7)."""
    m = build_matrix([{"material_id": "M", "property": "P"}], ["M"], ["P"])
    d = m.as_dict()
    assert set(d.keys()) == {"materials", "properties", "cells"}
    assert d["materials"] == ["M"]
    assert d["properties"] == ["P"]
    assert d["cells"] == [{"material_id": "M", "property": "P", "count": 1, "gap": False}]


def test_dataclasses_are_frozen() -> None:
    """Датаклассы неизменяемы / frozen dataclasses (§5.2.7 house style)."""
    cell = MatrixCell("M", "P", 1, False)
    matrix = CoverageMatrix(("M",), ("P",), (cell,))
    for obj, attr, val in ((cell, "count", 9), (matrix, "materials", ())):
        try:
            setattr(obj, attr, val)
        except (AttributeError, TypeError):
            continue
        raise AssertionError("expected frozen dataclass to reject mutation")
