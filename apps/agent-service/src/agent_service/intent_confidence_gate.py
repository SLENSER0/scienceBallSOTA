"""§13.8 intent confidence gate — abstain/clarify on weak classification (§7.5).

The §13.8 classifier (:mod:`agent_service.intent_classifier`) returns an
:class:`~agent_service.intent_classifier.IntentClass` with a heuristic
``confidence`` but never *acts* on a weak or ambiguous result. This module adds
the missing gate: it decides whether to ``proceed`` with the chosen intent, ask
the user to ``clarify`` (near-tie between two classes), or fall back to
``schema_help`` when confidence is too low to trust.

Классификатор намерений выдаёт уверенность, но не решает, что делать при слабой
или неоднозначной классификации — этот шлюз добавляет такое решение.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_service.intent_classifier import IntentClass

GateAction = Literal["proceed", "clarify", "schema_help"]


@dataclass(frozen=True)
class GateDecision:
    """Routing decision for a classified intent (§13.8 gate / §7.5 Node 2).

    Fields
    ------
    action
        ``proceed`` — trust the intent; ``clarify`` — ask the user (near-tie);
        ``schema_help`` — abstain, offer schema help (low confidence) (действие).
    intent
        The chosen ``query_type`` echoed from the primary class (намерение).
    confidence
        The primary class confidence echoed unchanged (уверенность).
    reason
        Machine-readable cause: ``proceed`` | ``low_confidence`` | ``near_tie``
        (причина решения).
    """

    action: GateAction
    intent: str
    confidence: float
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view for agent state / logging (§7.3)."""
        return {
            "action": self.action,
            "intent": self.intent,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def gate_intent(
    primary: IntentClass,
    runner_up: IntentClass | None = None,
    *,
    low: float = 0.35,
    tie_margin: float = 0.1,
) -> GateDecision:
    """Gate a classified intent into a routing decision (§13.8).

    Rules (in precedence order):

    1. ``primary.confidence < low`` -> ``schema_help`` (reason ``low_confidence``);
       a below-``low`` confidence always wins, even over a near-tie.
    2. else if ``runner_up`` is given and the margin
       ``primary.confidence - runner_up.confidence < tie_margin`` ->
       ``clarify`` (reason ``near_tie``).
    3. else -> ``proceed`` (reason ``proceed``).

    ``intent`` and ``confidence`` always echo *primary*.

    Правила по приоритету: низкая уверенность -> помощь по схеме; близкая
    ничья -> уточнение; иначе -> продолжить.
    """
    if primary.confidence < low:
        action: GateAction = "schema_help"
        reason = "low_confidence"
    elif runner_up is not None and primary.confidence - runner_up.confidence < tie_margin:
        action = "clarify"
        reason = "near_tie"
    else:
        action = "proceed"
        reason = "proceed"
    return GateDecision(
        action=action,
        intent=primary.query_type,
        confidence=primary.confidence,
        reason=reason,
    )
