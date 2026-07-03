"""Absence operating-point tuner — split cells into gap vs miss by one threshold (§25.15).

The absence pipeline scores each empty cell with ``p_extractor_missed`` — the estimated
probability that the value *exists* but the extractor **missed** it (в отличие от genuine
gap, где значения нет в источнике). Choosing a single decision threshold ``t`` splits every
cell into two operating buckets:

* ``p_extractor_missed >= t`` → **possible_miss** (worth re-extraction / review),
* ``p_extractor_missed <  t`` → **genuine_gap** (accepted as truly absent).

This module sweeps ``t`` over a grid, scores each threshold against gold labels, and picks
the operating point that best avoids *mislabelling real misses as gaps*. Gold rows are dicts
``{"p_extractor_missed": float, "gold": "genuine_gap" | "possible_miss"}``.

Both scored rates are conditioned on the **gold-possible_miss** population (the cells that
truly hide a missed value):

* ``false_gap_rate`` — fraction of gold-possible_miss cells the threshold buries as
  ``genuine_gap`` (ложный пропуск — реальный промах, названный «дырой»),
* ``miss_recall`` — fraction of gold-possible_miss cells correctly surfaced as
  ``possible_miss``; ``false_gap_rate + miss_recall == 1`` when any such cell exists.

Because raising ``t`` can only move cells from possible_miss to genuine_gap,
``false_gap_rate`` is **non-decreasing** in ``t``. The best operating point minimises
``false_gap_rate``, breaking ties toward the **lowest** threshold (the most permissive point).

This module is deliberately distinct from its §25 neighbours:

* ``gap_priority_config`` tunes *gap weights*, not a decision threshold.
* ``selective_risk_coverage`` sweeps a confidence-abstain risk-coverage (AURC) curve.
* This module tunes one ``p_extractor_missed`` cutoff for the gap/miss dichotomy.

Empty ``rows`` yield ``false_gap_rate == 0.0`` (no misses to bury) with no ``ZeroDivision``.
"""

from __future__ import annotations

from dataclasses import dataclass

GENUINE_GAP = "genuine_gap"
POSSIBLE_MISS = "possible_miss"


def _default_thresholds() -> list[float]:
    """Grid ``0.0, 0.05, …, 1.00`` (21 points), rounded to avoid float drift."""
    return [round(i * 0.05, 2) for i in range(21)]


@dataclass(frozen=True)
class SweepPoint:
    """One threshold's absence operating point (§25.15).

    ``threshold`` is the decision cutoff (predict ``possible_miss`` iff
    ``p_extractor_missed >= threshold``). ``false_gap_rate`` and ``miss_recall`` are
    conditioned on the gold-possible_miss cells; ``n`` is the total row count scored.
    ``as_dict`` rounds the float rates to 4 decimals for stable output.
    """

    threshold: float
    false_gap_rate: float
    miss_recall: float
    n: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "threshold": self.threshold,
            "false_gap_rate": round(self.false_gap_rate, 4),
            "miss_recall": round(self.miss_recall, 4),
            "n": self.n,
        }


@dataclass(frozen=True)
class ThresholdSweep:
    """Full absence threshold sweep with the selected best operating point (§25.15).

    ``points`` holds one :class:`SweepPoint` per swept threshold (grid order).
    ``best_threshold`` minimises ``false_gap_rate`` (ties → lowest threshold) and
    ``best_false_gap_rate`` is that point's rate. ``as_dict`` nests each point.
    """

    points: list[SweepPoint]
    best_threshold: float
    best_false_gap_rate: float

    def as_dict(self) -> dict[str, object]:
        return {
            "points": [point.as_dict() for point in self.points],
            "best_threshold": self.best_threshold,
            "best_false_gap_rate": self.best_false_gap_rate,
        }


def _score_threshold(rows: list[dict], threshold: float) -> SweepPoint:
    """Score ``predict possible_miss iff p_extractor_missed >= threshold`` over ``rows``."""
    gold_miss = 0
    buried = 0  # gold-possible_miss predicted genuine_gap
    for row in rows:
        if row["gold"] != POSSIBLE_MISS:
            continue
        gold_miss += 1
        if float(row["p_extractor_missed"]) < threshold:
            buried += 1
    if gold_miss == 0:
        false_gap_rate = 0.0
        miss_recall = 0.0
    else:
        false_gap_rate = buried / gold_miss
        miss_recall = (gold_miss - buried) / gold_miss
    return SweepPoint(
        threshold=threshold,
        false_gap_rate=false_gap_rate,
        miss_recall=miss_recall,
        n=len(rows),
    )


def sweep_thresholds(rows: list[dict], thresholds: list[float] | None = None) -> ThresholdSweep:
    """Sweep ``p_extractor_missed`` cutoffs and pick the lowest-false_gap_rate point (§25.15).

    Evaluates one :class:`SweepPoint` per threshold under the predict-possible_miss-iff
    ``p_extractor_missed >= t`` rule (default grid ``0.0..1.0`` step ``0.05``), then selects
    the point with the smallest ``false_gap_rate``, breaking ties toward the lowest
    threshold. Empty ``rows`` scores every point at ``false_gap_rate == 0.0`` without raising.
    """
    grid = _default_thresholds() if thresholds is None else list(thresholds)
    points = [_score_threshold(rows, threshold) for threshold in grid]
    best = min(points, key=lambda point: (point.false_gap_rate, point.threshold))
    return ThresholdSweep(
        points=points,
        best_threshold=best.threshold,
        best_false_gap_rate=best.false_gap_rate,
    )
