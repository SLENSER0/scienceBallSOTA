"""Блок «что проверить пилотно» — pick conditions worth a pilot check (§24.11).

A report closes with a short list of conditions the reader should validate *pilotно*
(pilotly) before trusting them at scale. Two signals flag a condition:

- **low confidence** — the extracted/derived confidence is below a threshold, so the
  claim is shaky and a small experiment would sharpen it;
- **local-parameter dependence** — the result is known to hinge on local parameters
  (reactor geometry, batch, instrument), so it may not transfer to the reader's setup.

This module is the *selection* layer only: :func:`recommend_pilots` scores plain-dict
conditions and returns a sorted tuple of :class:`PilotRecommendation`. The
``report_sections`` renderer only prints pre-resolved text; it does not recompute here.

Each condition is ``{condition_id, confidence: float, local_dependence: bool}``. A
condition is recommended iff ``confidence < conf_threshold`` (strict) **or**
``local_dependence`` is true. ``priority`` is ``2`` when both triggers fire, else ``1``;
``reason`` is one of ``'low_confidence'``, ``'local_dependence'``,
``'low_confidence_and_local'``. Results sort by ``priority`` descending, then
``condition_id`` ascending. Strictly read-only: no graph, no writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger

_log = get_logger("pilot_recommendations")

# -- reason codes ----------------------------------------------------------
REASON_LOW_CONFIDENCE = "low_confidence"  # только низкая уверенность
REASON_LOCAL_DEPENDENCE = "local_dependence"  # только локальная зависимость
REASON_BOTH = "low_confidence_and_local"  # оба триггера сразу

# Default confidence threshold — strictly below this counts as *low*.
DEFAULT_CONF_THRESHOLD = 0.5


@dataclass(frozen=True)
class PilotRecommendation:
    """One condition flagged for pilot validation — что проверить пилотно (§24.11).

    ``condition_id`` identifies the condition; ``reason`` is one of
    :data:`REASON_LOW_CONFIDENCE`, :data:`REASON_LOCAL_DEPENDENCE`,
    :data:`REASON_BOTH`; ``priority`` is ``2`` when both triggers fire, else ``1``.
    """

    condition_id: str
    reason: str
    priority: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "reason": self.reason,
            "priority": int(self.priority),
        }


def recommend_pilots(
    conditions: list[dict],
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
) -> tuple[PilotRecommendation, ...]:
    """Select conditions to validate pilotно, ranked by priority (§24.11).

    Each condition is ``{condition_id, confidence: float, local_dependence: bool}``.
    A condition is recommended iff its ``confidence`` is strictly below
    ``conf_threshold`` **or** its ``local_dependence`` is true. ``priority`` is ``2``
    when both triggers fire, else ``1``; ``reason`` reflects which triggers fired.
    The returned tuple is sorted by ``priority`` descending, then ``condition_id``
    ascending. Empty input yields an empty tuple.
    """
    recs: list[PilotRecommendation] = []
    for cond in conditions:
        condition_id = str(cond["condition_id"])
        low_conf = float(cond["confidence"]) < conf_threshold
        local_dep = bool(cond["local_dependence"])

        if not (low_conf or local_dep):
            continue

        if low_conf and local_dep:
            reason, priority = REASON_BOTH, 2
        elif low_conf:
            reason, priority = REASON_LOW_CONFIDENCE, 1
        else:
            reason, priority = REASON_LOCAL_DEPENDENCE, 1

        recs.append(
            PilotRecommendation(
                condition_id=condition_id,
                reason=reason,
                priority=priority,
            )
        )

    recs.sort(key=lambda r: (-r.priority, r.condition_id))

    _log.info(
        "pilot_recommendations.built",
        n_conditions=len(conditions),
        n_recommended=len(recs),
        conf_threshold=conf_threshold,
    )
    return tuple(recs)
