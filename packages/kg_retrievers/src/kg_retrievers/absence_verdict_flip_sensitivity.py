"""§25.11 — verdict-flip sensitivity analysis for one absence cell.

:mod:`kg_retrievers.absence_bayes` gives a *point* estimate: for a fixed prior
π = P(exists) and recall ``r`` it returns P(extractor missed) and thresholds it
into a verdict. It never asks *how close to the edge* that verdict is, nor *what
recall* would flip it. This module inverts the Bayesian формула to answer both.

For a no-evidence cell the miss-posterior is::

    p_missed(π, r) = π(1 - r) / (π(1 - r) + (1 - π))

Solving ``p_missed = t`` for the recall gives the flip point::

    r* = 1 - t(1 - π) / (π(1 - t))

If ``r*`` lands outside ``[0, 1]`` the threshold ``t`` is unreachable for that
prior (the verdict cannot flip by varying recall alone), so we report ``None``.
The *margin* (p_missed минус порог) and a robustness flag say whether the current
verdict is comfortably held or teetering on the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# -- verdicts (mirrors absence_bayes) --------------------------------------
POSSIBLE_MISS = "possible_miss"  # extractor probably missed a datum (пропуск)
GENUINE_GAP = "genuine_gap"  # confident real absence (настоящий пробел)

# -- defaults --------------------------------------------------------------
POSSIBLE_MISS_AT = 0.60  # p_missed >= this -> possible_miss
ROBUST_MARGIN = 0.15  # |margin| >= this -> verdict is robust


def _clamp01(x: float) -> float:
    """Clamp ``x`` into the closed interval ``[0, 1]`` (§25.11 input hygiene)."""
    return max(0.0, min(float(x), 1.0))


@dataclass(frozen=True)
class FlipSensitivity:
    """How robustly a single absence cell holds its verdict, and where it flips.

    ``current_verdict`` is the thresholded call at the cell's own recall;
    ``current_p_missed`` is P(extractor missed) there. ``recall_to_flip`` is the
    recall at which p_missed would cross the ``possible_miss`` threshold, or
    ``None`` when that crossing is unreachable within ``[0, 1]``. ``margin`` is
    ``current_p_missed - threshold`` (signed); ``robust`` is ``|margin| >= robust_margin``.
    """

    current_verdict: str
    current_p_missed: float
    recall_to_flip: float | None
    margin: float
    robust: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "current_verdict": self.current_verdict,
            "current_p_missed": self.current_p_missed,
            "recall_to_flip": self.recall_to_flip,
            "margin": self.margin,
            "robust": self.robust,
        }


def p_missed(exists_prior: float, recall: float) -> float:
    """P(extractor missed | no evidence) = e(1-r) / (e(1-r) + (1-e)).

    ``exists_prior`` (e = π) and ``recall`` (r) are clamped to ``[0, 1]``. When the
    denominator collapses to 0 (e = 1 and r = 1: the datum surely exists and
    extraction never misses) a no-evidence cell cannot be a miss, so returns 0.
    """
    e = _clamp01(exists_prior)
    r = _clamp01(recall)
    num = e * (1.0 - r)
    denom = num + (1.0 - e)
    if denom <= 0.0:
        return 0.0
    return num / denom


def recall_for_p_missed(exists_prior: float, target_p: float) -> float | None:
    """Invert ``p_missed`` -> the recall at which it equals ``target_p``.

    Solves ``r = 1 - target_p(1 - e) / (e(1 - target_p))``. Returns ``None`` when
    the solution falls outside ``[0, 1]`` (the target is unreachable for this
    prior), or when a denominator collapses (e = 0, or target_p = 1).
    """
    e = _clamp01(exists_prior)
    t = _clamp01(target_p)
    denom = e * (1.0 - t)
    if denom <= 0.0:
        return None
    r = 1.0 - t * (1.0 - e) / denom
    if r < 0.0 or r > 1.0:
        return None
    return r


def analyze_flip(
    exists_prior: float,
    recall: float,
    *,
    possible_miss_at: float = POSSIBLE_MISS_AT,
    robust_margin: float = ROBUST_MARGIN,
) -> FlipSensitivity:
    """Assess how robustly one cell holds its verdict -> :class:`FlipSensitivity`.

    ``current_verdict`` is ``possible_miss`` when ``p_missed >= possible_miss_at``
    else ``genuine_gap``. ``margin = p_missed - possible_miss_at`` (signed);
    ``robust = |margin| >= robust_margin``. ``recall_to_flip`` is the recall that
    would put p_missed exactly on the threshold, or ``None`` if unreachable.
    """
    p = p_missed(exists_prior, recall)
    verdict = POSSIBLE_MISS if p >= possible_miss_at else GENUINE_GAP
    margin = p - possible_miss_at
    robust = abs(margin) >= robust_margin
    recall_to_flip = recall_for_p_missed(exists_prior, possible_miss_at)
    return FlipSensitivity(
        current_verdict=verdict,
        current_p_missed=p,
        recall_to_flip=recall_to_flip,
        margin=margin,
        robust=robust,
    )
