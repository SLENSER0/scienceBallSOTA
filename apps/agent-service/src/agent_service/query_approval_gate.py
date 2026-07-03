"""§13.21 human-in-the-loop gate — approve broad/expensive queries.

Перед запуском дорогого/широкого запроса агент может прервать выполнение и
запросить подтверждение пользователя. / Before running a broad or expensive
query the agent may interrupt and ask the user to approve it.

This module decides that HITL interrupt *purely* from a :class:`dict` query plan
and the ``ENABLE_HITL`` flag — no graph store, no LLM — so it is trivially
unit-testable. When HITL is disabled the gate is a no-op (never asks). When it is
enabled the plan is scanned for four independent triggers:

* ``broad_intent`` — намерение слишком широкое / intent in the broad set
  (``literature_summary`` / ``broad_overview``);
* ``graph_algo`` — план использует дорогой графовый алгоритм /
  ``"graph_algo"`` appears in ``plan["retrieval_strategy"]``;
* ``unbounded`` — нет ни числовых ограничений, ни сущностей / neither
  ``numeric_constraints`` nor ``entities`` bound the search;
* ``deep_traversal`` — обход глубже ``max_hops`` / ``plan["max_hops"]`` exceeds
  the ``max_hops`` limit.

Reasons are deduplicated and sorted; approval is needed iff at least one reason
fired. The interrupt type is always ``"approve_query"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INTERRUPT_TYPE = "approve_query"

# Намерения, считающиеся широкими / intents treated as broad.
_BROAD_INTENTS = frozenset({"literature_summary", "broad_overview"})


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Решение §13.21 HITL-ворот / a §13.21 HITL approval decision.

    * ``needs_approval`` — нужно ли подтверждение / whether the run must pause;
    * ``reasons`` — отсортированные уникальные причины / sorted, unique triggers;
    * ``interrupt_type`` — всегда ``"approve_query"`` / always ``"approve_query"``.
    """

    needs_approval: bool
    reasons: tuple[str, ...]
    interrupt_type: str = INTERRUPT_TYPE

    def as_dict(self) -> dict[str, Any]:
        """Render an orjson-safe plain dict."""
        return {
            "needs_approval": self.needs_approval,
            "reasons": list(self.reasons),
            "interrupt_type": self.interrupt_type,
        }


def decide_approval(plan: dict, enable_hitl: bool, max_hops: int = 3) -> ApprovalDecision:
    """Decide the §13.21 ``approve_query`` interrupt from ``plan`` and the flag.

    Когда ``enable_hitl`` False — ворота отключены / when HITL is off the gate never
    asks (``needs_approval`` False, empty reasons). Иначе собираем причины /
    otherwise the triggers below are collected, deduped and sorted.
    """
    if not enable_hitl:
        return ApprovalDecision(needs_approval=False, reasons=())

    reasons: set[str] = set()

    if plan.get("intent") in _BROAD_INTENTS:
        reasons.add("broad_intent")

    if "graph_algo" in (plan.get("retrieval_strategy") or ()):
        reasons.add("graph_algo")

    if not plan.get("numeric_constraints") and not plan.get("entities"):
        reasons.add("unbounded")

    if plan.get("max_hops", 0) > max_hops:
        reasons.add("deep_traversal")

    ordered = tuple(sorted(reasons))
    return ApprovalDecision(needs_approval=bool(ordered), reasons=ordered)
