"""Spec-exact §17.9 large-graph **minimap density grid** payload.

Строит downsampled-сетку плотности для Sigma/large-graph minimap (§17.9): узлы
раскладываются по фиксированной решётке ``cols × rows``, для каждой непустой ячейки
считается число узлов и относительная плотность ``count / max_count``.

Границы (``bounds``) выводятся из min/max координат ``x``/``y`` узлов. Узел точно на
верхней границе (``x == maxX`` или ``y == maxY``) зажимается в последнюю колонку/строку,
чтобы не выпасть за пределы решётки. Вырожденный случай (нулевая ширина/высота, все узлы
в одной точке) кладёт всё в колонку/строку ``0``.

Pure python — no store/graph access; caller passes plain node dicts with ``x``/``y``.
Kuzu note: custom node props are not queryable columns — callers RETURN base columns and
read coordinates via ``get_node()`` before assembling the ``nodes`` list.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MinimapCell:
    """Одна непустая ячейка сетки: позиция ``col``/``row``, ``count`` и ``density`` (§17.9)."""

    col: int
    row: int
    count: int
    density: float

    def as_dict(self) -> dict:
        """Plain-dict projection for the minimap JSON payload (§17.9)."""
        return {
            "col": self.col,
            "row": self.row,
            "count": self.count,
            "density": self.density,
        }


@dataclass(frozen=True)
class MinimapPayload:
    """Downsampled density-grid payload for the large-graph minimap (§17.9)."""

    cols: int
    rows: int
    bounds: tuple[float, float, float, float]
    cells: tuple[MinimapCell, ...]
    max_count: int

    def as_dict(self) -> dict:
        """Plain-dict projection: ``bounds`` -> named corners, ``cells`` -> list (§17.9)."""
        min_x, min_y, max_x, max_y = self.bounds
        return {
            "cols": self.cols,
            "rows": self.rows,
            "bounds": {
                "minX": min_x,
                "minY": min_y,
                "maxX": max_x,
                "maxY": max_y,
            },
            "cells": [cell.as_dict() for cell in self.cells],
            "max_count": self.max_count,
        }


def _bucket(value: float, lo: float, hi: float, n: int) -> int:
    """Bucket ``value`` in ``[lo, hi]`` into one of ``n`` bins, clamped to ``[0, n-1]``.

    Нулевая ширина (``hi == lo``) -> бин ``0``. Узел ровно на ``hi`` зажимается в ``n-1``.
    """
    span = hi - lo
    if span <= 0.0:
        return 0
    idx = int((value - lo) / span * n)
    if idx < 0:
        return 0
    if idx >= n:
        return n - 1
    return idx


def build_minimap(nodes: list[dict], *, cols: int = 16, rows: int = 16) -> MinimapPayload:
    """Build the §17.9 minimap density grid from node ``x``/``y`` coordinates.

    Границы берутся из min/max координат узлов; узлы бакетятся в решётку ``cols × rows``
    (узел на верхней границе зажимается в последнюю колонку/строку). Возвращаются только
    непустые ячейки, отсортированные по ``(row, col)``, с ``density = count / max_count``.

    Пустой ``nodes`` -> ``max_count == 0`` и ``cells == ()`` (границы нулевые).
    """
    if not nodes:
        return MinimapPayload(
            cols=cols,
            rows=rows,
            bounds=(0.0, 0.0, 0.0, 0.0),
            cells=(),
            max_count=0,
        )

    xs = [float(node["x"]) for node in nodes]
    ys = [float(node["y"]) for node in nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    counts: dict[tuple[int, int], int] = {}
    for x, y in zip(xs, ys, strict=True):
        col = _bucket(x, min_x, max_x, cols)
        row = _bucket(y, min_y, max_y, rows)
        counts[(col, row)] = counts.get((col, row), 0) + 1

    max_count = max(counts.values())
    cells = tuple(
        MinimapCell(col=col, row=row, count=count, density=count / max_count)
        for (col, row), count in sorted(counts.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    )

    return MinimapPayload(
        cols=cols,
        rows=rows,
        bounds=(min_x, min_y, max_x, max_y),
        cells=cells,
        max_count=max_count,
    )
