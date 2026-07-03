"""Absence triage action board — turn absence cells into a work queue (§25.11/§25.13).

An *absence map* (``confidence_of_absence`` / ``absence_map``) classifies every
``(material, property)`` cell into a status: ``COVERED`` (evidence exists),
``CONFIDENT_ABSENCE`` (empty cell that is a real gap), ``POSSIBLE_ABSENCE`` (empty but
below the confident band), ``UNKNOWN`` (recall too low to conclude), or ``RETRACTED``
(only retracted measurements — §25.12). Those are *diagnoses*; a curator still needs to
know **what to do next**. Триаж (triage) превращает диагноз в действие.

This module is a thin, store-free *planning* layer over already-classified cells (plain
dicts). :func:`bucket_for` maps a cell's status/verdict to one curator **action**:

- ``CONFIDENT_ABSENCE`` → ``INVESTIGATE`` — a real gap worth chasing in the wild;
- ``POSSIBLE_ABSENCE``  → ``EXTRACT_MORE`` — probably a miss; re-run extraction;
- ``RETRACTED``         → ``REVIEW_RETRACTION`` — the datum was pulled; review it;
- ``COVERED`` / ``UNKNOWN`` (or anything else) → ``SKIP`` — no action needed.

:func:`triage_absence` groups a batch of cells into a :class:`TriageBoard` (one
:class:`TriageBucket` per action) and builds a ``recommended_next`` shortlist —
``INVESTIGATE`` cells first, then ``EXTRACT_MORE`` — capped at ``top_n``, so a curator
opening the board sees the highest-leverage work at the top.

Status matching is case-insensitive (the source constants are lowercase strings such as
``"confident_absence"``; assertions may use uppercase enum-style names), and both the
``status`` and ``verdict`` keys are honoured. Strictly read-only: no graph, no writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger

_log = get_logger("absence_triage")

# -- curator actions (bucket keys) -----------------------------------------
INVESTIGATE = "INVESTIGATE"  # real gap → chase it in the wild (настоящий пробел)
EXTRACT_MORE = "EXTRACT_MORE"  # probable miss → re-run extraction (вероятный пропуск)
REVIEW_RETRACTION = "REVIEW_RETRACTION"  # datum retracted → review (отозвано)
SKIP = "SKIP"  # covered / unknown → no action (ничего не делать)

# Ordered action vocabulary so buckets and serialisation stay deterministic (§25.11).
ACTIONS: tuple[str, ...] = (INVESTIGATE, EXTRACT_MORE, REVIEW_RETRACTION, SKIP)

# Status/verdict (upper-cased) → action. Everything unlisted falls through to SKIP.
_STATUS_TO_ACTION: dict[str, str] = {
    "CONFIDENT_ABSENCE": INVESTIGATE,
    "POSSIBLE_ABSENCE": EXTRACT_MORE,
    "RETRACTED": REVIEW_RETRACTION,
    "COVERED": SKIP,
    "UNKNOWN": SKIP,
}

# Order in which actions feed the ``recommended_next`` shortlist (INVESTIGATE first).
_RECOMMEND_ORDER: tuple[str, ...] = (INVESTIGATE, EXTRACT_MORE)

# Default cap on the ``recommended_next`` shortlist.
DEFAULT_TOP_N = 5


@dataclass(frozen=True)
class TriageBucket:
    """All cells sharing one curator action — действие + его очередь (§25.11).

    ``action`` is one of :data:`ACTIONS`; ``count`` is ``len(items)``; ``items`` are the
    cell dicts assigned to the action, in input order.
    """

    action: str
    count: int
    items: list[dict]

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "count": self.count,
            "items": list(self.items),
        }


@dataclass(frozen=True)
class TriageBoard:
    """Action board — one bucket per action + a ranked shortlist (§25.11/§25.13).

    ``buckets`` maps every action in :data:`ACTIONS` to its :class:`TriageBucket` (empty
    buckets included, so the board shape is stable). ``recommended_next`` is the
    highest-leverage shortlist: ``INVESTIGATE`` cells first, then ``EXTRACT_MORE``,
    capped at ``top_n``.
    """

    buckets: dict[str, TriageBucket]
    recommended_next: list[dict]

    def as_dict(self) -> dict[str, Any]:
        return {
            "buckets": {k: v.as_dict() for k, v in self.buckets.items()},
            "recommended_next": list(self.recommended_next),
        }


def _status_of(cell: dict) -> str:
    """Upper-cased status/verdict of a cell — ``status`` wins, then ``verdict`` (§25.11).

    A cell carries its diagnosis under either key (different producers use different
    names); missing/empty values normalise to ``""`` and fall through to ``SKIP``.
    """
    raw = cell.get("status") or cell.get("verdict") or ""
    return str(raw).strip().upper()


def bucket_for(cell: dict) -> str:
    """Map one absence cell to its curator action (§25.11/§25.13).

    Reads the cell's status/verdict (case-insensitive, ``status`` preferred over
    ``verdict``) and returns one of :data:`ACTIONS`. ``CONFIDENT_ABSENCE`` →
    ``INVESTIGATE``, ``POSSIBLE_ABSENCE`` → ``EXTRACT_MORE``, ``RETRACTED`` →
    ``REVIEW_RETRACTION``; ``COVERED`` / ``UNKNOWN`` and every unrecognised value →
    ``SKIP``.
    """
    return _STATUS_TO_ACTION.get(_status_of(cell), SKIP)


def triage_absence(cells: list[dict], *, top_n: int = DEFAULT_TOP_N) -> TriageBoard:
    """Group absence cells into an action board with a ranked shortlist (§25.11/§25.13).

    Assigns every cell to an action via :func:`bucket_for`, builds one
    :class:`TriageBucket` per action in :data:`ACTIONS` (empty buckets kept), and
    composes ``recommended_next`` by concatenating the ``INVESTIGATE`` items then the
    ``EXTRACT_MORE`` items (each in input order) and truncating to ``max(top_n, 0)``.
    Empty input yields all-zero buckets and an empty shortlist.
    """
    grouped: dict[str, list[dict]] = {action: [] for action in ACTIONS}
    for cell in cells:
        grouped[bucket_for(cell)].append(cell)

    buckets = {
        action: TriageBucket(action=action, count=len(items), items=list(items))
        for action, items in grouped.items()
    }

    shortlist: list[dict] = []
    for action in _RECOMMEND_ORDER:
        shortlist.extend(grouped[action])
    recommended_next = shortlist[: max(top_n, 0)]

    _log.info(
        "absence_triage.built",
        n_cells=len(cells),
        n_investigate=buckets[INVESTIGATE].count,
        n_extract_more=buckets[EXTRACT_MORE].count,
        n_review_retraction=buckets[REVIEW_RETRACTION].count,
        n_skip=buckets[SKIP].count,
        n_recommended=len(recommended_next),
    )
    return TriageBoard(buckets=buckets, recommended_next=recommended_next)
