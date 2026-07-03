"""GraphRAG full-vs-incremental index mode decision (§11.4).

Выбор режима индексации — before (re)building the GraphRAG index the pipeline must
decide whether to do a *full* rebuild from scratch or an *incremental* update that
touches only the changed slice. This module is a pure planner: given three facts —
does the backend support incremental updates, is there a prior build to extend, and
how large is the delta (``changed_ratio`` in ``[0, 1]``) — it returns an
:class:`IndexModePlan` naming the chosen ``mode`` and the ``reason``.

An incremental build is chosen only when it is both possible and worthwhile: the
backend supports it, a prior build exists, and the delta is below
``full_rebuild_threshold`` (exclusive). Otherwise a full rebuild is planned and the
``reason`` names the single blocker. The module holds no state and touches no store —
it just decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Reason codes explaining the chosen mode (§11.4). Exactly one applies per decision.
REASON_NO_INCREMENTAL_SUPPORT = "no_incremental_support"
REASON_NO_PRIOR_BUILD = "no_prior_build"
REASON_LARGE_DELTA = "large_delta"
REASON_INCREMENTAL_OK = "incremental_ok"

# The two index modes the planner can pick.
MODE_FULL = "full"
MODE_INCREMENTAL = "incremental"


@dataclass(frozen=True)
class IndexModePlan:
    """Planned GraphRAG index build mode (§11.4).

    ``mode`` is ``'full'`` or ``'incremental'``; ``reason`` is one of the
    ``REASON_*`` codes; ``changed_ratio`` echoes the delta size the decision saw.
    """

    mode: str
    reason: str
    changed_ratio: float

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{mode, reason, changed_ratio}``."""
        return {
            "mode": self.mode,
            "reason": self.reason,
            "changed_ratio": self.changed_ratio,
        }


def decide_mode(
    supports_incremental: bool,
    has_prior_build: bool,
    changed_ratio: float,
    full_rebuild_threshold: float = 0.5,
) -> IndexModePlan:
    """Pick ``full`` vs ``incremental`` for a GraphRAG index build (§11.4).

    Returns ``incremental`` only when the backend supports it, a prior build exists,
    and ``0 <= changed_ratio < full_rebuild_threshold`` (threshold exclusive — a delta
    exactly at the threshold triggers a full rebuild). Otherwise returns ``full`` with
    the ``reason`` naming the first blocker encountered, checked in priority order:
    missing support, then missing prior build, then a too-large delta.

    Выбор режима: инкрементальная сборка возможна лишь при поддержке бэкендом,
    наличии предыдущей сборки и малой доле изменений; иначе — полная пересборка.
    """
    if not supports_incremental:
        return IndexModePlan(MODE_FULL, REASON_NO_INCREMENTAL_SUPPORT, changed_ratio)
    if not has_prior_build:
        return IndexModePlan(MODE_FULL, REASON_NO_PRIOR_BUILD, changed_ratio)
    if not (0.0 <= changed_ratio < full_rebuild_threshold):
        return IndexModePlan(MODE_FULL, REASON_LARGE_DELTA, changed_ratio)
    return IndexModePlan(MODE_INCREMENTAL, REASON_INCREMENTAL_OK, changed_ratio)
