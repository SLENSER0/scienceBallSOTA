"""Pairwise divergence matrix over a measurement group for the Evidence Inspector (§15.4).

Матрица попарных расхождений для группы измерений. The
:mod:`kg_retrievers.contradiction_detector` classifies a *single* pair of
measurements; the Evidence Inspector, however, wants to show an operator the full
``N×N`` picture over a whole measurement group at once — which values diverge from
which, and by how much.

This module builds that matrix. Given a list of measurement dicts (keys
``id`` / ``value_normalized`` and optionally ``ci_low`` / ``ci_high``) it computes
the symmetric relative-divergence matrix ``|a-b| / max(|a|,|b|)`` and the set of
conflicting pairs — pairs whose divergence exceeds ``rel_tol`` **and** (when both
sides carry a confidence interval) whose intervals do not overlap. Перекрывающиеся
доверительные интервалы подавляют конфликт.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["PairwiseDivergence", "pairwise_divergence"]

# A measurement dict: at least ``id`` / ``value_normalized``, optionally CI bounds.
Measurement = dict[str, Any]


@dataclass(frozen=True)
class PairwiseDivergence:
    """The pairwise divergence matrix for one measurement group (§15.4).

    ``ids`` are the measurement ids in row/column order. ``matrix[i][j]`` is the
    relative divergence ``|a-b| / max(|a|,|b|)`` (rounded to 4 dp; diagonal is
    ``0.0`` and the matrix is symmetric). ``conflict_pairs`` lists ``(id_i, id_j)``
    with ``i<j`` where the divergence exceeds ``rel_tol`` and, when both sides have a
    confidence interval, the intervals do not overlap. ``max_divergence`` is the
    largest off-diagonal entry (``0.0`` for a single measurement).
    """

    ids: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    conflict_pairs: tuple[tuple[str, str], ...]
    max_divergence: float

    def as_dict(self) -> dict:
        return {
            "ids": list(self.ids),
            "matrix": [list(row) for row in self.matrix],
            "conflict_pairs": [list(pair) for pair in self.conflict_pairs],
            "max_divergence": self.max_divergence,
        }


def _as_float(value: Any) -> float | None:
    """Best-effort float, or ``None`` when the value is missing/unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative_divergence(a: float, b: float) -> float:
    """Relative point-value gap ``|a-b| / max(|a|,|b|)`` (``0.0`` when both zero)."""
    scale = max(abs(a), abs(b))
    if scale == 0.0:
        return 0.0
    return abs(a - b) / scale


def _has_ci(m: Measurement) -> bool:
    """True when a measurement carries a fully-parsed confidence interval."""
    return _as_float(m.get("ci_low")) is not None and _as_float(m.get("ci_high")) is not None


def _ci_overlaps(a: Measurement, b: Measurement) -> bool:
    """True when both sides have confidence intervals that overlap (перекрытие ДИ).

    When either side lacks a CI there is nothing to overlap, so the answer is
    ``False`` (the divergence test alone then decides the conflict).
    """
    if not (_has_ci(a) and _has_ci(b)):
        return False
    a_low, a_high = _as_float(a["ci_low"]), _as_float(a["ci_high"])
    b_low, b_high = _as_float(b["ci_low"]), _as_float(b["ci_high"])
    return a_low <= b_high and b_low <= a_high


def pairwise_divergence(
    measurements: list[Measurement], *, rel_tol: float = 0.2
) -> PairwiseDivergence:
    """Build the pairwise divergence matrix for a measurement group (§15.4).

    Each measurement contributes one row/column keyed by its ``id``. Entry
    ``matrix[i][j]`` is the relative divergence between the two normalized values,
    rounded to 4 dp; the diagonal is ``0.0`` and the matrix is symmetric. A pair
    ``(i, j)`` with ``i<j`` is a conflict when its divergence exceeds ``rel_tol``
    **and** (when both sides carry a CI) the intervals do not overlap.
    """
    ids = tuple(str(m.get("id")) for m in measurements)
    values = [_as_float(m.get("value_normalized")) for m in measurements]
    n = len(measurements)

    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
    conflict_pairs: list[tuple[str, str]] = []
    max_divergence = 0.0

    for i in range(n):
        for j in range(i + 1, n):
            va, vb = values[i], values[j]
            if va is None or vb is None:
                continue
            div = round(_relative_divergence(va, vb), 4)
            matrix[i][j] = div
            matrix[j][i] = div
            if div > max_divergence:
                max_divergence = div
            if div > rel_tol and not _ci_overlaps(measurements[i], measurements[j]):
                conflict_pairs.append((ids[i], ids[j]))

    return PairwiseDivergence(
        ids=ids,
        matrix=tuple(tuple(row) for row in matrix),
        conflict_pairs=tuple(conflict_pairs),
        max_divergence=max_divergence,
    )
