"""Dense adjacency-matrix + CSV export for a KG subgraph — §22.

Чистый stdlib-строитель плотной матрицы смежности и её CSV-рендер: на вход —
обычные ``dict`` узлов и рёбер (уже прочитанные из графа), на выход — матрица
``AdjacencyMatrix`` и CSV-текст, который читают R/pandas/matplotlib (heatmap).
Модуль НЕ трогает store/БД/LLM/часы и отличается от ``neo4j_import_csv``
(bulk-import CSV) и ``asset_graph`` (внутренний DAG сборки): здесь —
числовая матрица для внешнего анализа/визуализации.

Pure stdlib dense adjacency-matrix builder and CSV renderer: it takes plain node
and edge ``dict``s (already read from the graph) and returns an ``AdjacencyMatrix``
plus CSV text that R/pandas/matplotlib read (heatmaps). It touches no store/DB/
LLM/clock and is distinct from ``neo4j_import_csv`` (bulk import) and
``asset_graph`` (internal build DAG): this is a numeric matrix for external use.

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN
base columns and read the rest via ``get_node``; к моменту, когда узлы и рёбра
доходят сюда, они уже несут нужные поля, поэтому store здесь не нужен.

Entry points:

- :class:`AdjacencyMatrix` — метки, строки-веса и флаг направленности;
- :func:`build_matrix` — построить матрицу из узлов и рёбер;
- :func:`to_csv` — отрендерить матрицу в CSV (stdlib ``csv`` quoting).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Вес ребра по умолчанию, если ключ веса отсутствует/пустой (§22).
# Default edge weight when the weight key is missing/empty.
_DEFAULT_WEIGHT = 1.0


@dataclass(frozen=True, slots=True)
class AdjacencyMatrix:
    """Плотная матрица смежности подграфа KG — §22.

    ``labels`` — метки узлов в порядке ввода (совпадает с порядком строк/столбцов);
    ``rows[i][j]`` — накопленный вес рёбер из узла ``i`` в узел ``j``; ``directed``
    отмечает, была ли матрица построена как ориентированная. ``labels`` are node
    labels in input order (matching row/column order); ``rows[i][j]`` is the
    accumulated edge weight from node ``i`` to node ``j``; ``directed`` records
    whether the matrix was built directed.
    """

    labels: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]
    directed: bool

    def as_dict(self) -> dict[str, Any]:
        """JSON-представление; порядок ``labels`` сохранён, строки — списки."""
        return {
            "labels": list(self.labels),
            "rows": [list(row) for row in self.rows],
            "directed": self.directed,
        }


def _edge_weight(edge: dict, weight_key: str) -> float:
    """Вес ребра: значение по ``weight_key`` либо ``_DEFAULT_WEIGHT``.

    Отсутствующий, ``None`` или нечисловой вес трактуется как значение по
    умолчанию. A missing, ``None`` or non-numeric weight falls back to the default.
    """
    value = edge.get(weight_key)
    if value is None:
        return _DEFAULT_WEIGHT
    try:
        return float(value)
    except (TypeError, ValueError):
        return _DEFAULT_WEIGHT


def build_matrix(
    nodes: list[dict],
    edges: list[dict],
    *,
    directed: bool = True,
    weight_key: str = "weight",
) -> AdjacencyMatrix:
    """Построить :class:`AdjacencyMatrix` из узлов и рёбер — §22.

    Порядок строк/столбцов = порядок узлов во входе (по их ``id``); ``label``
    берётся из узла (``label``/``name``), иначе — сам ``id``. ``cell[i][j]``
    накапливает вес каждого ребра ``i -> j`` (по умолчанию ``1.0``); при
    ``directed=False`` дополнительно отражается в ``cell[j][i]``. Рёбра с
    неизвестным концом (нет такого ``id`` среди узлов) игнорируются.

    Row/column order equals node input order (by ``id``); the label comes from the
    node (``label``/``name``), else the ``id`` itself. ``cell[i][j]`` accumulates
    each ``i -> j`` edge weight (default ``1.0``); when ``directed=False`` it is
    also mirrored into ``cell[j][i]``. Edges with an unknown endpoint (no matching
    node ``id``) are ignored.
    """
    labels: list[str] = []
    index: dict[Any, int] = {}
    for node in nodes:
        node_id = node.get("id")
        if node_id in index:
            continue
        index[node_id] = len(labels)
        label = node.get("label") or node.get("name") or node_id
        labels.append(str(label))

    size = len(labels)
    matrix: list[list[float]] = [[0.0] * size for _ in range(size)]

    for edge in edges:
        src = _first(edge, ("source", "from", "src", "start"))
        dst = _first(edge, ("target", "to", "dst", "end"))
        if src not in index or dst not in index:
            continue
        i, j = index[src], index[dst]
        weight = _edge_weight(edge, weight_key)
        matrix[i][j] += weight
        if not directed and i != j:
            matrix[j][i] += weight

    return AdjacencyMatrix(
        labels=tuple(labels),
        rows=tuple(tuple(row) for row in matrix),
        directed=directed,
    )


def _first(edge: dict, keys: Sequence[str]) -> Any:
    """Первое присутствующее (не ``None``) значение среди ``keys`` в ``edge``.

    First present (non-``None``) value among ``keys`` in ``edge`` (``None`` if none).
    """
    for key in keys:
        value = edge.get(key)
        if value is not None:
            return value
    return None


def to_csv(m: AdjacencyMatrix) -> str:
    """Отрендерить :class:`AdjacencyMatrix` в CSV-текст — §22.

    Первая строка — заголовок: пустая верхняя-левая ячейка (``""``), затем метки
    столбцов. Далее по строке на узел: сначала его метка, затем веса. Кавычки/
    экранирование — стандартный stdlib ``csv``; строки через ``\\r\\n`` (диалект
    ``excel``). The header row starts with an empty top-left cell then the column
    labels; each following row is a node label followed by its weights.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["", *m.labels])
    for label, row in zip(m.labels, m.rows, strict=True):
        writer.writerow([label, *row])
    return buffer.getvalue()
