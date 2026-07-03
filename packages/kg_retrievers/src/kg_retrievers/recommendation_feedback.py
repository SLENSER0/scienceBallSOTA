"""Feedback-adjusted recommendation re-ranking for the §24.12 feedback loop.

RU: Корректировка ранжирования рекомендаций по обратной связи «полезно / не
полезно» (§24.12: «feedback loop влияет на ranking»). Для каждого элемента
``feedback_delta = up * up_weight - down * down_weight`` и
``adjusted_score = base_score + feedback_delta``. Затем элементы пересортированы по
``adjusted_score`` (убывание), при равенстве — по ``item_id`` (возрастание), и им
присваивается ``rank`` от 1 до n. Элемент без записи в ``feedback`` получает дельту
0.0 и остаётся неизменным.
EN: Adjusts recommendation ranking from useful / not-useful feedback (§24.12:
"feedback loop влияет на ranking"). For each item ``feedback_delta = up * up_weight
- down * down_weight`` and ``adjusted_score = base_score + feedback_delta``. Items are
re-sorted by ``adjusted_score`` (desc), ties broken by ``item_id`` (asc), and assigned
``rank`` 1..n. An item absent from ``feedback`` gets delta 0.0 and is unchanged.

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read the rest via ``get_node()`` before
handing item dicts to :func:`apply_feedback`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# §24.12 feedback-loop defaults: each up/down vote nudges the score by ±0.1.
DEFAULT_UP_WEIGHT = 0.1
DEFAULT_DOWN_WEIGHT = 0.1


@dataclass(frozen=True)
class AdjustedRecommendation:
    """Frozen feedback-adjusted recommendation (§24.12).

    ``base_score`` is the pre-feedback ranking score; ``feedback_delta`` is the signed
    nudge from up/down votes; ``adjusted_score == base_score + feedback_delta``; and
    ``rank`` is the 1-based position after re-sorting.
    """

    item_id: str
    base_score: float
    feedback_delta: float
    adjusted_score: float
    rank: int

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§24.12, house style)."""
        return {
            "item_id": self.item_id,
            "base_score": self.base_score,
            "feedback_delta": self.feedback_delta,
            "adjusted_score": self.adjusted_score,
            "rank": self.rank,
        }


def apply_feedback(
    items: list[dict],
    feedback: dict[str, dict],
    *,
    up_weight: float = DEFAULT_UP_WEIGHT,
    down_weight: float = DEFAULT_DOWN_WEIGHT,
) -> list[AdjustedRecommendation]:
    """Re-rank recommendations by useful / not-useful feedback (§24.12).

    ``items`` is a list of ``{"item_id", "base_score"}`` dicts; ``feedback`` maps an
    ``item_id`` to ``{"up": int, "down": int}``. For each item
    ``feedback_delta = up * up_weight - down * down_weight`` and
    ``adjusted_score = base_score + feedback_delta``. An item with no feedback entry
    gets delta 0.0 and keeps its base score. Results are sorted by ``adjusted_score``
    (desc), ties broken by ``item_id`` (asc), and assigned ``rank`` 1..n. Empty
    ``items`` yields ``[]``.
    """
    scored: list[tuple[float, str, float, float]] = []
    for item in items:
        item_id = item["item_id"]
        base_score = float(item["base_score"])
        votes = feedback.get(item_id)
        if votes is None:
            feedback_delta = 0.0
        else:
            up = int(votes.get("up", 0))
            down = int(votes.get("down", 0))
            feedback_delta = up * up_weight - down * down_weight
        adjusted_score = base_score + feedback_delta
        scored.append((adjusted_score, item_id, base_score, feedback_delta))

    # Sort by adjusted_score desc, then item_id asc for deterministic tie-breaking.
    scored.sort(key=lambda row: (-row[0], row[1]))

    ranked: list[AdjustedRecommendation] = []
    for rank, (adjusted_score, item_id, base_score, feedback_delta) in enumerate(scored, start=1):
        ranked.append(
            AdjustedRecommendation(
                item_id=item_id,
                base_score=base_score,
                feedback_delta=feedback_delta,
                adjusted_score=adjusted_score,
                rank=rank,
            )
        )
    return ranked
