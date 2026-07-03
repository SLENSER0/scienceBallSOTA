"""Absence-map entropy: single-scalar epistemic-uncertainty KPI (§25.11).

Pure-python reduction of an *absence map* — a flat list of ``CoverageCell``-shaped
dicts, each carrying a verdict ``status`` — to one scalar that measures how uncertain
the map's verdict distribution is. :mod:`absence_map` only produces status *counts*; it
never computes entropy. This module fills that gap: :func:`map_entropy` tallies the
status frequencies and returns the Shannon entropy (base 2) plus a normalized share of
the maximum possible entropy for the observed number of distinct statuses.

Энтропия карты неизвестного: скалярный KPI эпистемической неопределённости распределения
вердиктов ячеек (Шеннон, log2) с нормировкой на максимум для числа различных статусов.

A fully-covered map (one status) has zero entropy and ``normalized == 0.0``; a map split
evenly between two statuses has ``entropy_bits == 1.0`` and ``normalized == 1.0``. Cells
missing the status key are bucketed as ``'unknown'``. The result is a frozen dataclass
exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

# Status token used when a cell lacks the status key (§25.11).
UNKNOWN = "unknown"


@dataclass(frozen=True)
class MapEntropy:
    """Epistemic-uncertainty summary of an absence map's verdict distribution (§25.11).

    - ``n_cells`` — number of input cells;
    - ``counts`` — histogram ``{status: count}`` over the map;
    - ``entropy_bits`` — Shannon entropy (log2) of the status frequencies, in bits;
    - ``normalized`` — ``entropy_bits / log2(k)`` for ``k`` distinct statuses
      (``0.0`` when ``k <= 1``), i.e. entropy as a share of its maximum;
    - ``dominant_status`` — most frequent status, ties broken alphabetically
      (empty string for an empty map).
    """

    n_cells: int
    counts: dict[str, int]
    entropy_bits: float
    normalized: float
    dominant_status: str

    def as_dict(self) -> dict:
        return {
            "n_cells": self.n_cells,
            "counts": dict(self.counts),
            "entropy_bits": self.entropy_bits,
            "normalized": self.normalized,
            "dominant_status": self.dominant_status,
        }


def map_entropy(cells: list[dict], *, status_key: str = "status") -> MapEntropy:
    """Reduce an absence map to its verdict-distribution entropy KPI (§25.11).

    Each cell's ``status_key`` value is coerced to ``str``; cells missing the key are
    bucketed as ``'unknown'``. Entropy is Shannon's ``-Σ p·log2(p)`` over the status
    frequencies. ``normalized`` divides that by ``log2(k)`` where ``k`` is the number of
    distinct statuses, giving ``0.0`` when ``k <= 1`` (a single-category or empty map).
    ``dominant_status`` is the most frequent status with alphabetical tie-breaking.
    """
    counts: Counter[str] = Counter()
    for cell in cells:
        if status_key in cell:
            counts[str(cell[status_key])] += 1
        else:
            counts[UNKNOWN] += 1

    n_cells = len(cells)
    k = len(counts)

    entropy_bits = 0.0
    if n_cells > 0:
        for count in counts.values():
            p = count / n_cells
            entropy_bits -= p * math.log2(p)

    normalized = entropy_bits / math.log2(k) if k > 1 else 0.0

    # Most frequent status; ties broken alphabetically (min status wins).
    dominant_status = min(counts, key=lambda s: (-counts[s], s)) if counts else ""

    return MapEntropy(
        n_cells=n_cells,
        counts=dict(counts),
        entropy_bits=entropy_bits,
        normalized=normalized,
        dominant_status=dominant_status,
    )
