"""Retraction summary over a set of observations — сводка по ретракциям (§25.16).

Given a list of *measurement* nodes (flattened dicts, as returned by
:func:`kg_retrievers.retractions.active_measurements` with
``include_retracted=True``), this module rolls them up into a compact
*retraction report*: how many observations there are in total, how many are
soft-retracted vs still active, a histogram of *why* they were withdrawn
(причина ретракции — the ``retraction_reason`` prop), and the retracted share.

The notion of "retracted" is **not** re-implemented here: we reuse the exact
predicate that :func:`kg_retrievers.retractions.is_retracted` delegates to
(:func:`~kg_retrievers.retractions._is_retracted_node`), so a node counts as
retracted here iff it would count as retracted there. Per §25.12 the ``retracted``
tombstone lives in the JSON ``props`` catch-all rather than a queryable column, so
these dicts already carry it flattened at the top level.

Pure Python and read-only: it reads no store and writes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from kg_retrievers.retractions import _is_retracted_node

# Bucket for a retracted observation that carries no ``retraction_reason`` prop
# (причина не указана) — keeps the histogram total equal to ``retracted``.
UNSPECIFIED_REASON = "unspecified"


@dataclass(frozen=True)
class RetractionReport:
    """Retraction roll-up: totals, active/retracted split, reason histogram, ratio (§25.16).

    ``total`` is every observation seen; ``retracted`` + ``active`` always sum to
    it. ``by_reason`` is a key-sorted histogram of ``retraction_reason`` over the
    retracted observations only (its counts sum to ``retracted``).
    ``retracted_ratio`` is ``retracted / total`` — ``0.0`` on an empty input.
    """

    total: int
    retracted: int
    active: int
    by_reason: dict[str, int]
    retracted_ratio: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "retracted": self.retracted,
            "active": self.active,
            "by_reason": dict(self.by_reason),
            "retracted_ratio": self.retracted_ratio,
        }


def retraction_report(measurements: Iterable[dict[str, Any]]) -> RetractionReport:
    """Summarize the retraction state of ``measurements`` (§25.16).

    Each flattened observation dict is classified with the shared predicate
    :func:`~kg_retrievers.retractions._is_retracted_node` (the dict-form of
    :func:`~kg_retrievers.retractions.is_retracted`). Retracted observations are
    bucketed by their ``retraction_reason`` into a key-sorted ``by_reason``
    histogram; those without a reason fall under :data:`UNSPECIFIED_REASON`. The
    ``retracted_ratio`` is ``retracted / total``, defined as ``0.0`` for an empty
    input. ``retracted`` and ``active`` always sum back to ``total``.
    """
    items = list(measurements)
    retracted_nodes = [m for m in items if _is_retracted_node(m)]
    total = len(items)
    retracted = len(retracted_nodes)

    by_reason: dict[str, int] = {}
    for node in retracted_nodes:
        reason = str(node.get("retraction_reason") or UNSPECIFIED_REASON)
        by_reason[reason] = by_reason.get(reason, 0) + 1

    return RetractionReport(
        total=total,
        retracted=retracted,
        active=total - retracted,
        by_reason=dict(sorted(by_reason.items())),
        retracted_ratio=(retracted / total if total else 0.0),
    )
