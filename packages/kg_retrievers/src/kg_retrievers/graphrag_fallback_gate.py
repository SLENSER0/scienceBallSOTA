"""GraphRAG fallback gate (§11.12).

Обзорный (broad) вопрос — a wide, survey-style query best answered from
community summaries. GraphRAG (community-summary retrieval) is only worth
invoking when three things hold at once: the feature is enabled, an active
GraphRAG build exists (``build_status == 'built'``), and the query intent is
broad. This module makes that ternary decision explicit and, when GraphRAG is
declined, names the concrete cause and the fallback retriever to use instead.

The gate is pure logic: it takes already-computed inputs (feature flag, build
status string, broad-intent verdict) and returns a frozen :class:`GateDecision`.
It never touches the graph or the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Note attached to a GraphRAG-routed answer — signals the обзорный (survey) mode.
_MODE_NOTE = "обзорный ответ на основе community summaries"

# Build-status value that marks an active, usable GraphRAG build (§11.12).
_BUILT = "built"

# Warning causes, most-specific-first, mirroring the gate's decision order.
_WARN_DISABLED = "graphrag disabled"
_WARN_NO_BUILD = "no active build"
_WARN_NOT_BROAD = "not a broad query"


@dataclass(frozen=True)
class GateDecision:
    """Outcome of the GraphRAG fallback gate (§11.12).

    ``use_graphrag`` is ``True`` only on the all-clear path; then ``mode_note`` is
    set and ``warning`` is ``None``. On any declined path ``use_graphrag`` is
    ``False``, ``mode_note`` is ``None``, ``fallback_mode`` names the retriever to
    fall back to, and ``warning`` states the cause.
    """

    use_graphrag: bool
    fallback_mode: str
    warning: str | None
    mode_note: str | None

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{use_graphrag, fallback_mode, warning, mode_note}``."""
        return {
            "use_graphrag": self.use_graphrag,
            "fallback_mode": self.fallback_mode,
            "warning": self.warning,
            "mode_note": self.mode_note,
        }


def decide_graphrag(
    *,
    enabled: bool,
    build_status: str | None,
    is_broad_intent: bool,
    fallback: str = "hybrid",
) -> GateDecision:
    """Decide whether to route a query to GraphRAG (§11.12).

    Returns ``use_graphrag=True`` iff all three hold: ``enabled`` is set, an active
    build exists (``build_status == 'built'``), and ``is_broad_intent`` is set. On
    that path the decision carries ``mode_note`` (обзорный mode) and no warning.

    Otherwise ``use_graphrag`` is ``False`` with ``fallback_mode=fallback`` and a
    ``warning`` naming the first blocking cause, checked in order: the feature is
    off (``'graphrag disabled'``), then no active build (``'no active build'`` — any
    ``build_status`` other than ``'built'``, including ``None``), then a narrow
    query (``'not a broad query'``). A narrow/numeric query (``is_broad_intent``
    ``False``) is therefore never routed to GraphRAG.
    """
    if not enabled:
        return GateDecision(False, fallback, _WARN_DISABLED, None)
    if build_status != _BUILT:
        return GateDecision(False, fallback, _WARN_NO_BUILD, None)
    if not is_broad_intent:
        return GateDecision(False, fallback, _WARN_NOT_BROAD, None)
    return GateDecision(True, fallback, None, _MODE_NOTE)
