"""Weighted multi-criteria decision analysis over a TechnologyComparison (§24.13).

Сравнительный анализ технологий: взвешенная многокритериальная оценка (MCDA).
Pure-python weighted MCDA operating on an alternatives×criteria matrix drawn
from a ``TechnologyComparison`` (§24.13 ``scores`` / ``normalized_units`` plus
user-supplied criterion weights). Each criterion column is min-max normalized to
[0,1] — benefit criteria keep their orientation while cost criteria are inverted
so that "larger raw = worse" becomes "smaller normalized = worse". A weighted sum
of normalized scores yields a total per alternative; alternatives are ranked
1..n by descending total, ties broken by ``alternative_id`` ascending.

- **normalize_criterion** — линейная min-max нормализация одного столбца-критерия
  (benefit=False инвертирует cost-критерий; вырожденный столбец → все 1.0).
- **score_alternatives** — взвешивает нормализованные оценки и ранжирует
  альтернативы (sorted by weighted_total desc, ties by id asc).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MCDAResult:
    """Результат MCDA для одной альтернативы / one alternative's scored ranking.

    - ``alternative_id`` — идентификатор альтернативы / alternative identifier.
    - ``raw_scores`` — исходные значения критериев / raw per-criterion values.
    - ``normalized_scores`` — нормализованные [0,1] значения / normalized values.
    - ``weighted_total`` — взвешенная сумма / sum(normalized * weight).
    - ``rank`` — ранг 1..n (1 = лучший) / 1-based rank (1 is best).
    """

    alternative_id: str
    raw_scores: dict[str, float]
    normalized_scores: dict[str, float]
    weighted_total: float
    rank: int

    def as_dict(self) -> dict[str, Any]:
        """Сериализуемое представление / serializable mapping of all fields."""
        return {
            "alternative_id": self.alternative_id,
            "raw_scores": dict(self.raw_scores),
            "normalized_scores": dict(self.normalized_scores),
            "weighted_total": self.weighted_total,
            "rank": self.rank,
        }


def normalize_criterion(values: dict[str, float], *, benefit: bool) -> dict[str, float]:
    """Min-max normalize one criterion column to [0,1] (§24.13).

    ``values`` maps ``alternative_id -> raw_value`` for a single criterion. For a
    benefit criterion (``benefit=True``) the maximum maps to 1.0 and the minimum
    to 0.0; for a cost criterion (``benefit=False``) the orientation is inverted
    so the minimum raw value (cheapest/best) maps to 1.0. An all-equal column
    (zero span) maps every alternative to 1.0 — the criterion cannot discriminate,
    so no alternative is penalized on it.
    """
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    span = hi - lo
    if span <= 0.0:
        return dict.fromkeys(values, 1.0)
    if benefit:
        return {k: (float(v) - lo) / span for k, v in values.items()}
    return {k: (hi - float(v)) / span for k, v in values.items()}


def score_alternatives(
    matrix: dict[str, dict[str, float]],
    weights: dict[str, float],
    directions: dict[str, bool],
) -> list[MCDAResult]:
    """Weighted MCDA ranking of alternatives (§24.13).

    ``matrix`` maps ``alternative_id -> {criterion: raw_value}``; ``weights`` maps
    ``criterion -> weight``; ``directions`` maps ``criterion -> benefit?`` (True
    for benefit criteria, False for cost). Each criterion column is normalized via
    :func:`normalize_criterion`, then each alternative's ``weighted_total`` is the
    sum of ``normalized * weight`` over criteria. Results are sorted by
    ``weighted_total`` descending with ties broken by ``alternative_id`` ascending,
    and ranked 1..n. An empty ``matrix`` yields an empty list.
    """
    if not matrix:
        return []
    criteria = list(weights.keys())
    # Normalize each criterion column across all alternatives.
    normalized_by_criterion: dict[str, dict[str, float]] = {}
    for criterion in criteria:
        column = {alt: float(row.get(criterion, 0.0)) for alt, row in matrix.items()}
        benefit = directions.get(criterion, True)
        normalized_by_criterion[criterion] = normalize_criterion(column, benefit=benefit)

    partial: list[tuple[str, dict[str, float], dict[str, float], float]] = []
    for alt, row in matrix.items():
        raw = {c: float(row.get(c, 0.0)) for c in criteria}
        normalized = {c: normalized_by_criterion[c][alt] for c in criteria}
        total = sum(normalized[c] * float(weights[c]) for c in criteria)
        partial.append((alt, raw, normalized, total))

    # Sort by weighted_total desc, ties broken by alternative_id asc.
    partial.sort(key=lambda item: (-item[3], item[0]))

    return [
        MCDAResult(
            alternative_id=alt,
            raw_scores=raw,
            normalized_scores=normalized,
            weighted_total=total,
            rank=idx,
        )
        for idx, (alt, raw, normalized, total) in enumerate(partial, start=1)
    ]
