"""Idempotent gap-scan reconciliation — pure diff → run counters (§15.2/§15.6).

:mod:`~kg_retrievers.gap_lifecycle` mutates a :class:`KuzuGraphStore` one Gap at a
time (resolve / reopen / auto-resolve). There is no *pure* function that, given the
gaps a previous scan left behind and the gaps a fresh scan just detected, reports
what a :class:`GapScanRun` should record — сколько создано / переоткрыто /
автозакрыто. This module fills that hole: a side-effect-free diff over two lists of
gap dicts, keyed by ``dedup_key``, producing a frozen :class:`ScanReconciliation`.

Because it touches no store it is trivially **idempotent** (§15.6): re-running a
scan whose detected set equals the still-open previous set yields all-zero counters.

Lifecycle rules (пропуск: open → resolved → (reopen) → open):

* detected key **absent** from previous            → *created*
* detected key present with ``status=='resolved'``  → *reopened* (снова открыт)
* previous ``status=='open'`` key **not** detected  → *auto_resolved* (покрыт)
* previous ``status`` in ``{acknowledged, dismissed}`` never auto-resolves — a
  curator's manual decision is preserved (ручное решение сохраняется)
* keys active in both scans (overlapping, non-resolved)  → *still_open*

Each gap dict carries a ``dedup_key``; previous gaps additionally carry a
``status`` (a missing/blank status is treated as ``open``, matching a fresh Gap in
:mod:`~kg_retrievers.gap_lifecycle`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
# Curator-set statuses that a scan must never auto-resolve — ручные, сохраняются.
MANUAL_STATUSES = frozenset({"acknowledged", "dismissed"})


@dataclass(frozen=True)
class ScanReconciliation:
    """Pure diff of one gap scan against the previous one (§15.2/§15.6).

    ``created`` / ``reopened`` / ``auto_resolved`` / ``still_open`` are the sorted
    ``dedup_key`` tuples in each bucket; the ``gaps_*`` ints are their counts, ready
    to stamp onto a :class:`GapScanRun`. ``still_open`` deliberately has no counter —
    it is the steady-state carry-over, not an event.
    """

    created: tuple[str, ...]
    reopened: tuple[str, ...]
    auto_resolved: tuple[str, ...]
    still_open: tuple[str, ...]
    gaps_created: int
    gaps_reopened: int
    gaps_auto_resolved: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "reopened": list(self.reopened),
            "auto_resolved": list(self.auto_resolved),
            "still_open": list(self.still_open),
            "gaps_created": self.gaps_created,
            "gaps_reopened": self.gaps_reopened,
            "gaps_auto_resolved": self.gaps_auto_resolved,
        }


def _status_of(gap: dict[str, Any]) -> str:
    """Lifecycle status of a previous gap; missing/blank defaults to ``open``."""
    return str(gap.get("status") or STATUS_OPEN)


def reconcile_scan(previous: list[dict], detected: list[dict]) -> ScanReconciliation:
    """Diff a fresh scan against the previous gaps — no side effects (§15.2/§15.6).

    ``previous`` gaps each carry ``dedup_key`` + ``status``; ``detected`` gaps carry
    ``dedup_key``. Applies the module's lifecycle rules and returns a frozen
    :class:`ScanReconciliation` whose bucket tuples are sorted. Pure and idempotent:
    identical previous-open and detected sets yield all-zero counters.
    """
    prev_status: dict[str, str] = {str(g["dedup_key"]): _status_of(g) for g in previous}
    detected_keys: set[str] = {str(g["dedup_key"]) for g in detected}

    created: set[str] = set()
    reopened: set[str] = set()
    still_open: set[str] = set()

    for key in detected_keys:
        status = prev_status.get(key)
        if status is None:
            created.add(key)  # brand-new gap this scan surfaced
        elif status == STATUS_RESOLVED:
            reopened.add(key)  # was closed, но снова обнаружен
        else:
            still_open.add(key)  # overlapping open / manual — carried over

    auto_resolved: set[str] = set()
    for key, status in prev_status.items():
        if key in detected_keys:
            continue
        if status == STATUS_OPEN:
            auto_resolved.add(key)  # open gap the fresh scan no longer sees → покрыт
        elif status in MANUAL_STATUSES:
            still_open.add(key)  # manual decision preserved, never auto-resolved

    return ScanReconciliation(
        created=tuple(sorted(created)),
        reopened=tuple(sorted(reopened)),
        auto_resolved=tuple(sorted(auto_resolved)),
        still_open=tuple(sorted(still_open)),
        gaps_created=len(created),
        gaps_reopened=len(reopened),
        gaps_auto_resolved=len(auto_resolved),
    )
