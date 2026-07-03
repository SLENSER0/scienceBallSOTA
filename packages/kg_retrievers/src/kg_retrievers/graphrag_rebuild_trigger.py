"""GraphRAG rebuild sensor — pure trigger decision (§11.10).

The §11.10 Dagster *sensor* wakes on a schedule and must decide whether to kick off a
(costly) GraphRAG community rebuild. This module is the store-free, side-effect-free
**decision core** behind that sensor: given a handful of scalar signals it returns a
single :class:`RebuildDecision`, so the sensor body stays a thin adapter and the policy
itself is unit-testable in isolation. Sensor (сенсор) только считывает сигналы —
решение о пересборке принимает эта чистая функция.

:func:`decide_rebuild` evaluates triggers in a fixed **priority order** and stops at the
first that fires:

1. ``failed_build`` — the last build ended in ``last_build_status == "failed"``; a broken
   index must be rebuilt regardless of freshness or corpus size (сломанный индекс важнее
   всего);
2. ``stale`` — ``hours_since_last >= max_age_hours``; the index has aged past its window;
3. ``corpus_growth`` — ``n_new_docs >= doc_threshold``; enough new documents have landed
   to justify a rebuild;
4. otherwise ``up_to_date`` with ``should_rebuild=False``.

Priority is strict: ``failed_build`` wins over ``corpus_growth`` (and everything else)
when several conditions hold at once. ``pending_docs`` always echoes the passed
``n_new_docs`` so a caller can log the backlog even when no rebuild is triggered.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# -- trigger reasons (stable string vocabulary) ----------------------------
FAILED_BUILD = "failed_build"  # last build failed → rebuild (сломанная сборка)
STALE = "stale"  # index aged past its window (индекс устарел)
CORPUS_GROWTH = "corpus_growth"  # enough new docs landed (прирост корпуса)
UP_TO_DATE = "up_to_date"  # nothing to do (актуально)

# Sentinel value of ``last_build_status`` that signals a broken index.
_FAILED_STATUS = "failed"


@dataclass(frozen=True)
class RebuildDecision:
    """Outcome of the §11.10 rebuild sensor: fire-or-not plus a human reason."""

    should_rebuild: bool
    reason: str
    pending_docs: int

    def as_dict(self) -> dict[str, Any]:
        """Serialise all three fields for logging / sensor cursors (round-trips)."""
        return asdict(self)


def decide_rebuild(
    n_new_docs: int,
    doc_threshold: int,
    hours_since_last: float,
    max_age_hours: float,
    last_build_status: str,
) -> RebuildDecision:
    """Decide whether the GraphRAG index should be rebuilt (§11.10).

    Triggers are checked in strict priority order — ``failed_build`` → ``stale`` →
    ``corpus_growth`` — and the first match wins; otherwise the index is ``up_to_date``.
    ``pending_docs`` always echoes ``n_new_docs``.
    """
    if last_build_status == _FAILED_STATUS:
        return RebuildDecision(True, FAILED_BUILD, n_new_docs)
    if hours_since_last >= max_age_hours:
        return RebuildDecision(True, STALE, n_new_docs)
    if n_new_docs >= doc_threshold:
        return RebuildDecision(True, CORPUS_GROWTH, n_new_docs)
    return RebuildDecision(False, UP_TO_DATE, n_new_docs)
