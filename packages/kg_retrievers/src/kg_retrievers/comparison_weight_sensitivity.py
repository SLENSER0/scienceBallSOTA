"""Weight-sensitivity of an MCDA ranking (§24.13).

Анализ чувствительности взвешенной MCDA-оценки к изменению весов критериев.
While :mod:`kg_retrievers.mcda_scoring` ranks alternatives **once** under a fixed
weight vector, a comparison report also needs to know *how trustworthy that #1
pick is*: would a small, defensible shift of the weights hand the crown to a
different alternative? This module answers that on top of an already-normalized
alternatives×criteria score matrix (every value already in ``[0,1]``).

The perturbation model is the classic "one-at-a-time" sweep: each criterion's
weight is nudged **upward** by multiples of ``step`` while the remaining weights
are **renormalized** proportionally so the vector keeps summing to 1. The
smallest upward nudge (across all criteria) that changes which alternative is #1
is the ``min_flip_delta``; the criterion responsible is the ``flipping_criterion``.
A top pick that survives every sweep is reported as ``robust``.

- **weighted_totals** — взвешенная сумма по строкам (raw ``sum(value * weight)``),
  без ренормализации весов; основа как базового, так и возмущённого ранжирования.
- **analyze_sensitivity** — ищет наименьший сдвиг веса, меняющий лидера (§24.13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Matrix = dict[str, dict[str, float]]
Weights = dict[str, float]


@dataclass(frozen=True)
class SensitivityResult:
    """Итог анализа чувствительности лидера MCDA / verdict for the #1 alternative.

    - ``top_id`` — базовый лидер при исходных весах / baseline #1 alternative id.
    - ``robust`` — True, если ни одно возмущение веса не сменило лидера / no sweep
      dethroned the leader within the perturbation range.
    - ``min_flip_delta`` — наименьший добавленный к одному критерию вес, сменивший
      лидера / smallest upward weight nudge that flipped #1 (None when robust).
    - ``flipping_criterion`` — критерий, чьё усиление сменило лидера / the criterion
      responsible for the flip (None when robust).
    """

    top_id: str
    robust: bool
    min_flip_delta: float | None
    flipping_criterion: str | None

    def as_dict(self) -> dict[str, Any]:
        """Сериализуемое представление / serializable mapping of all fields."""
        return {
            "top_id": self.top_id,
            "robust": bool(self.robust),
            "min_flip_delta": self.min_flip_delta,
            "flipping_criterion": self.flipping_criterion,
        }


def weighted_totals(matrix: Matrix, weights: Weights) -> dict[str, float]:
    """Weighted sum per alternative over a pre-normalized matrix (§24.13).

    ``matrix`` maps ``alternative_id -> {criterion: value}`` with every ``value``
    already in ``[0,1]``; ``weights`` maps ``criterion -> weight``. Each
    alternative's total is the raw ``sum(value * weight)`` over the weighted
    criteria (a missing cell counts as ``0.0``); the weight vector is **not**
    renormalized here, so a single-criterion matrix weighted at ``1.0`` returns
    that criterion's column verbatim. An empty ``matrix`` raises ``ValueError``.
    """
    if not matrix:
        raise ValueError("weighted_totals: matrix is empty")
    totals: dict[str, float] = {}
    for alt, row in matrix.items():
        totals[alt] = sum(float(row.get(c, 0.0)) * float(w) for c, w in weights.items())
    return totals


def _leader(totals: dict[str, float]) -> str:
    """Return the #1 alternative: max total, ties broken by ``alternative_id`` asc."""
    return min(totals, key=lambda alt: (-totals[alt], alt))


def _normalize(weights: Weights) -> dict[str, float]:
    """Scale weights to sum to 1.0 (monotone — leaves any ranking unchanged)."""
    total = sum(float(w) for w in weights.values())
    if total <= 0.0:
        raise ValueError("analyze_sensitivity: weights must sum to a positive value")
    return {c: float(w) / total for c, w in weights.items()}


def _perturb(weights_norm: dict[str, float], criterion: str, delta: float) -> dict[str, float]:
    """Nudge ``criterion`` up by ``delta``, renormalizing the rest to keep sum 1.

    The other criteria are scaled by ``(1 - w_c - delta) / (1 - w_c)`` so the
    perturbed vector still sums to 1 and their relative proportions are preserved.
    Callers guarantee ``delta < 1 - w_c`` so the remaining mass stays positive.
    """
    w_c = weights_norm[criterion]
    rest = 1.0 - w_c
    new_c = w_c + delta
    scale = (1.0 - new_c) / rest
    return {c: (new_c if c == criterion else w * scale) for c, w in weights_norm.items()}


def analyze_sensitivity(matrix: Matrix, weights: Weights, step: float = 0.05) -> SensitivityResult:
    """Find the smallest weight shift that dethrones the MCDA leader (§24.13).

    Computes the baseline #1 alternative under ``weights`` (normalized to sum 1),
    then, for each criterion independently, increases that criterion's weight by
    ``step, 2*step, 3*step, …`` — renormalizing the other weights proportionally —
    until either the leader changes or the criterion would absorb all remaining
    weight. The smallest such nudge over all criteria is ``min_flip_delta`` and the
    criterion that produced it is ``flipping_criterion`` (ties broken by criterion
    key ascending). If no sweep changes the leader, the result is ``robust`` with
    both fields ``None``. An empty ``matrix`` or non-positive ``step`` (or weights
    summing to ``<= 0``) raises ``ValueError``.
    """
    if not matrix:
        raise ValueError("analyze_sensitivity: matrix is empty")
    if step <= 0.0:
        raise ValueError("analyze_sensitivity: step must be positive")

    weights_norm = _normalize(weights)
    baseline_top = _leader(weighted_totals(matrix, weights_norm))

    best_delta: float | None = None
    best_criterion: str | None = None
    for criterion in sorted(weights_norm):
        w_c = weights_norm[criterion]
        room = 1.0 - w_c  # criterion can absorb at most this much extra weight
        k = 1
        while k * step < room:
            delta = k * step
            perturbed = _perturb(weights_norm, criterion, delta)
            if _leader(weighted_totals(matrix, perturbed)) != baseline_top:
                if best_delta is None or delta < best_delta:
                    best_delta, best_criterion = delta, criterion
                break
            k += 1

    if best_delta is None:
        return SensitivityResult(
            baseline_top,
            robust=True,
            min_flip_delta=None,
            flipping_criterion=None,
        )
    return SensitivityResult(
        baseline_top,
        robust=False,
        min_flip_delta=best_delta,
        flipping_criterion=best_criterion,
    )
