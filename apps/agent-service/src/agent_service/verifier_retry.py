"""§13.16 цикл повтора верификатора / verifier retry loop (pure python).

After the verifier scores a draft answer the graph, its report may carry
violations. Some are *fixable* by another retrieval+planning pass — a missing
piece of evidence («нет доказательства») or an empty retrieval («пустая
выборка») can often be resolved by re-planning the query. Others (style,
mixed units, …) will not improve on retry, so the graph should proceed to
answer synthesis regardless.

:func:`route_after_verify` encodes that routing decision deterministically: if
the report holds any fixable violation *and* the attempt budget is not yet
spent, it routes back to ``query_planner`` and consumes one attempt; otherwise
it routes forward to ``answer_synthesizer`` leaving the counter untouched. The
returned :class:`RetryDecision` also surfaces the ids of the still-unresolved
fixable violations, so callers can log or display what triggered the retry.

Deterministic and dependency-free — see :mod:`agent_service.answer_validator`
for the numeric-claim check and :mod:`agent_service.verifier` for the
graph-backed grounding that produces these reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Severities that a re-plan/re-retrieve pass can plausibly resolve (исправимые).
# "unsupported" is the tag :mod:`agent_service.verifier` puts on ungrounded
# citations and uncited measurable numbers (L-43/L-49): re-retrieval may surface
# the missing evidence, so it must route back to the planner like the others.
FIXABLE_SEVERITIES: frozenset[str] = frozenset(
    {"missing_evidence", "empty_retrieval", "unsupported"}
)

# Routing targets in the graph.
_NODE_RETRY = "query_planner"
_NODE_FORWARD = "answer_synthesizer"


@dataclass(frozen=True)
class RetryDecision:
    """Result of §13.16 post-verify routing / решение о маршрутизации.

    ``next_node`` names the graph node to run next, ``attempts`` is the updated
    attempt counter (incremented only when routing back to ``query_planner``),
    ``reason`` is an RU/EN human-readable note, and ``unresolved`` holds the ids
    of the fixable violations that motivated (or would have motivated) a retry.
    """

    next_node: str
    attempts: int
    reason: str
    unresolved: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{next_node, attempts, reason, unresolved}`` (unresolved as list)."""
        return {
            "next_node": self.next_node,
            "attempts": self.attempts,
            "reason": self.reason,
            "unresolved": list(self.unresolved),
        }


def is_fixable(violation: dict) -> bool:
    """True only for a violation whose severity is in :data:`FIXABLE_SEVERITIES`.

    Исправимо только «missing_evidence» и «empty_retrieval» — всё остальное False.
    """
    return violation.get("severity") in FIXABLE_SEVERITIES


def _violation_id(violation: dict, index: int) -> str:
    """Best-effort stable id for a violation — its ``id`` or a positional fallback."""
    raw = violation.get("id")
    return str(raw) if raw is not None else f"violation_{index}"


def route_after_verify(
    verifier_report: dict,
    attempts: int,
    max_attempts: int = 3,
) -> RetryDecision:
    """Decide the next graph node after verification / выбрать следующий узел.

    If ``verifier_report`` carries any fixable violation *and* ``attempts <
    max_attempts``, route back to ``query_planner`` and increment ``attempts``.
    Otherwise route forward to ``answer_synthesizer`` with ``attempts``
    unchanged. The returned attempts value never exceeds ``max_attempts``.
    """
    violations = verifier_report.get("violations", []) or []
    unresolved = tuple(_violation_id(v, i) for i, v in enumerate(violations) if is_fixable(v))

    if unresolved and attempts < max_attempts:
        return RetryDecision(
            next_node=_NODE_RETRY,
            attempts=attempts + 1,
            reason=f"исправимые нарушения / fixable violations: {', '.join(unresolved)}",
            unresolved=unresolved,
        )

    if unresolved:
        reason = "бюджет попыток исчерпан / attempt budget spent"
    else:
        reason = "нет исправимых нарушений / no fixable violations"
    return RetryDecision(
        next_node=_NODE_FORWARD,
        attempts=attempts,
        reason=reason,
        unresolved=unresolved,
    )
