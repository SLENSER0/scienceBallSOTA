"""Tests for the dense adjacency-matrix + CSV export — §22.

Hand-checkable: маленькие графы, точные значения ячеек и CSV-строк.
Hand-checkable: tiny graphs with exact cell values and CSV rows.
"""

from __future__ import annotations

import csv
import io

from kg_retrievers.graph_adjacency_matrix import (
    AdjacencyMatrix,
    build_matrix,
    to_csv,
)


def _nodes_ab() -> list[dict]:
    return [{"id": "A"}, {"id": "B"}]


def test_directed_single_edge_default_weight() -> None:
    """A->B, вес по умолчанию -> [[0,1],[0,0]]."""
    m = build_matrix(_nodes_ab(), [{"source": "A", "target": "B"}])
    assert m.rows == ((0.0, 1.0), (0.0, 0.0))
    assert m.directed is True


def test_undirected_mirrors() -> None:
    """directed=False -> симметрично: [[0,1],[1,0]]."""
    m = build_matrix(
        _nodes_ab(),
        [{"source": "A", "target": "B"}],
        directed=False,
    )
    assert m.rows == ((0.0, 1.0), (1.0, 0.0))
    assert m.directed is False


def test_parallel_edges_accumulate() -> None:
    """Два параллельных A->B накапливают вес до 2.0."""
    m = build_matrix(
        _nodes_ab(),
        [
            {"source": "A", "target": "B"},
            {"source": "A", "target": "B"},
        ],
    )
    assert m.rows[0][1] == 2.0
    assert m.rows[1][0] == 0.0


def test_explicit_weight_key() -> None:
    """Явный weight_key суммирует заданные веса."""
    m = build_matrix(
        _nodes_ab(),
        [
            {"source": "A", "target": "B", "w": 1.5},
            {"source": "A", "target": "B", "w": 0.5},
        ],
        weight_key="w",
    )
    assert m.rows[0][1] == 2.0


def test_self_loop_sets_diagonal() -> None:
    """Петля A->A ставит вес в cell[0][0]."""
    m = build_matrix(_nodes_ab(), [{"source": "A", "target": "A"}])
    assert m.rows[0][0] == 1.0
    assert m.rows[0][1] == 0.0


def test_self_loop_undirected_not_double_counted() -> None:
    """Петля при directed=False не удваивается на диагонали."""
    m = build_matrix(
        _nodes_ab(),
        [{"source": "A", "target": "A"}],
        directed=False,
    )
    assert m.rows[0][0] == 1.0


def test_unknown_endpoint_ignored() -> None:
    """Ребро с неизвестным концом игнорируется."""
    m = build_matrix(
        _nodes_ab(),
        [
            {"source": "A", "target": "Z"},
            {"source": "Q", "target": "B"},
            {"source": "A", "target": "B"},
        ],
    )
    assert m.rows == ((0.0, 1.0), (0.0, 0.0))


def test_labels_preserve_input_order() -> None:
    """labels/строки в порядке ввода узлов; label из поля label/name."""
    nodes = [
        {"id": "B", "label": "Beta"},
        {"id": "A", "name": "Alpha"},
        {"id": "C"},
    ]
    m = build_matrix(nodes, [])
    assert m.labels == ("Beta", "Alpha", "C")
    assert m.as_dict()["labels"] == ["Beta", "Alpha", "C"]


def test_as_dict_shapes() -> None:
    """as_dict даёт списки и сохраняет порядок/направленность."""
    m = build_matrix(_nodes_ab(), [{"source": "A", "target": "B"}])
    d = m.as_dict()
    assert d["labels"] == ["A", "B"]
    assert d["rows"] == [[0.0, 1.0], [0.0, 0.0]]
    assert d["directed"] is True


def test_to_csv_header_first_cell_empty_and_row_count() -> None:
    """CSV: первая ячейка заголовка пустая; строк = len(labels)+1."""
    m = build_matrix(_nodes_ab(), [{"source": "A", "target": "B"}])
    text = to_csv(m)
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0][0] == ""
    assert parsed[0] == ["", "A", "B"]
    assert len(parsed) == len(m.labels) + 1


def test_to_csv_row_prefixed_by_label() -> None:
    """Каждая строка CSV начинается с метки узла, затем веса."""
    m = build_matrix(_nodes_ab(), [{"source": "A", "target": "B"}])
    parsed = list(csv.reader(io.StringIO(to_csv(m))))
    assert parsed[1] == ["A", "0.0", "1.0"]
    assert parsed[2] == ["B", "0.0", "0.0"]


def test_to_csv_quotes_labels_with_commas() -> None:
    """stdlib csv экранирует метки с запятыми."""
    nodes = [{"id": "A", "label": "a,b"}, {"id": "B"}]
    m = build_matrix(nodes, [])
    text = to_csv(m)
    assert '"a,b"' in text
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[1][0] == "a,b"


def test_empty_graph() -> None:
    """Пустой граф -> пустые labels/rows и только строка-заголовок."""
    m = build_matrix([], [])
    assert m == AdjacencyMatrix(labels=(), rows=(), directed=True)
    parsed = list(csv.reader(io.StringIO(to_csv(m))))
    assert parsed == [[""]]


def test_duplicate_node_ids_collapse() -> None:
    """Повторный id узла не создаёт лишнюю строку/столбец."""
    nodes = [{"id": "A"}, {"id": "A"}, {"id": "B"}]
    m = build_matrix(nodes, [{"source": "A", "target": "B"}])
    assert m.labels == ("A", "B")
    assert m.rows == ((0.0, 1.0), (0.0, 0.0))
