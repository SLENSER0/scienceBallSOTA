"""Построитель матрицы покрытия «материал × свойство» для ``GET /gaps/matrix`` (§5.2.7).

Чистый построитель плотной/разрежённой матрицы покрытия для панели пробелов
(§5.2.7 Gap Dashboard). :mod:`api_gateway.routers.gaps` содержит эндпоинт
``gaps_matrix``, но не имеет переиспользуемого чистого построителя — этот модуль
на чистом stdlib его предоставляет: считает число строк-экспериментов на каждую
пару ``(material_id, property)``, помечает пробел при ``count < min_count`` и
выдаёт плотную сетку ячеек; :func:`to_sparse` оставляет только ячейки-пробелы.

Pure builder of the dense/sparse material×property coverage matrix for the
§5.2.7 Gap Dashboard (``GET /gaps/matrix``). ``routers/gaps.py`` has a
``gaps_matrix`` endpoint but no reusable pure builder — this stdlib-only module
supplies one: it counts experiment rows per ``(material_id, property)`` pair,
flags a gap when ``count < min_count``, and emits a dense cell grid;
:func:`to_sparse` keeps only the gap cells.

* :class:`MatrixCell` — одна ячейка ``(material, property)`` / a single cell.
* :class:`CoverageMatrix` — плотная матрица покрытия / dense coverage matrix.
* :func:`build_matrix` — строки → плотная матрица / rows → dense matrix.
* :func:`to_sparse` — матрица → только пробелы / matrix → gap-only cell dicts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MatrixCell:
    """Одна ячейка покрытия ``(material, property)`` (§5.2.7).

    A single coverage cell. ``count`` is the number of experiment rows for this
    ``(material_id, property)`` pair; ``gap`` is ``True`` when the pair is under
    the required minimum count. :meth:`as_dict` yields the wire form.
    """

    material_id: str
    property: str
    count: int
    gap: bool

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление ячейки / wire form (§5.2.7)."""
        return {
            "material_id": self.material_id,
            "property": self.property,
            "count": self.count,
            "gap": self.gap,
        }


@dataclass(frozen=True, slots=True)
class CoverageMatrix:
    """Плотная матрица покрытия «материал × свойство» (§5.2.7).

    Dense coverage matrix. ``materials`` and ``properties`` are the ordered axes;
    ``cells`` is the full dense grid (one :class:`MatrixCell` per pair, so
    ``len(cells) == len(materials) * len(properties)``). :meth:`as_dict` yields
    the wire form with cells expanded via :meth:`MatrixCell.as_dict`.
    """

    materials: tuple[str, ...]
    properties: tuple[str, ...]
    cells: tuple[MatrixCell, ...]

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление матрицы / wire form (§5.2.7)."""
        return {
            "materials": list(self.materials),
            "properties": list(self.properties),
            "cells": [c.as_dict() for c in self.cells],
        }


def build_matrix(
    rows: Sequence[Mapping],
    materials: Sequence[str],
    properties: Sequence[str],
    *,
    min_count: int = 1,
) -> CoverageMatrix:
    """Построить плотную матрицу покрытия из строк-экспериментов (§5.2.7).

    Build the dense material×property coverage matrix. Each row is a mapping with
    ``material_id`` and ``property`` keys; rows are counted per pair. The emitted
    grid is dense over ``materials × properties`` (in the given axis order), so a
    pair with zero rows yields ``count == 0``. A cell is a gap when
    ``count < min_count``.

    :param rows: строки-эксперименты / experiment rows.
    :param materials: ось материалов / material axis (order preserved).
    :param properties: ось свойств / property axis (order preserved).
    :param min_count: минимум строк, ниже которого пара — пробел / gap threshold.
    """
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        counts[(row["material_id"], row["property"])] += 1
    cells: list[MatrixCell] = []
    for material_id in materials:
        for prop in properties:
            count = counts[(material_id, prop)]
            cells.append(MatrixCell(material_id, prop, count, count < min_count))
    return CoverageMatrix(tuple(materials), tuple(properties), tuple(cells))


def to_sparse(m: CoverageMatrix) -> list[dict]:
    """Разрежённое представление: только ячейки-пробелы (§5.2.7).

    Sparse view: the wire form of only those cells where ``gap`` is ``True``.
    """
    return [c.as_dict() for c in m.cells if c.gap]
