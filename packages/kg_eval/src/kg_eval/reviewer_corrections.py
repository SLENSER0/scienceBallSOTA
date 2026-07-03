"""Reviewer corrections per 100 extractions (§18.10 System metric / §12.3 curation decisions).

Aggregates curation decision events (§12.3) into the
``reviewer_corrections_per_100_extractions`` system metric. Each event carries a
``decision`` in {accepted, rejected, merged, split, corrected}; only the
non-``accepted`` decisions count as reviewer *corrections*.

Distinct from acceptance-rate metrics — this counts the *editing effort* a reviewer
spends per 100 extractions, normalising against the total extraction volume.

Правки ревьюера на 100 извлечений: доля решений куратора, потребовавших вмешательства.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Recognised curation decisions (§12.3). ``accepted`` is NOT a correction.
DECISIONS: tuple[str, ...] = ("accepted", "rejected", "merged", "split", "corrected")
CORRECTION_DECISIONS: tuple[str, ...] = ("rejected", "merged", "split", "corrected")


@dataclass(frozen=True)
class ReviewerCorrectionStats:
    """Aggregated reviewer-correction counts + the per-100-extractions rate."""

    total_extractions: int
    accepted: int
    rejected: int
    merged: int
    split: int
    corrected: int
    corrections_per_100: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "total_extractions": int(self.total_extractions),
            "accepted": int(self.accepted),
            "rejected": int(self.rejected),
            "merged": int(self.merged),
            "split": int(self.split),
            "corrected": int(self.corrected),
            "corrections_per_100": round(float(self.corrections_per_100), 4),
        }


def count_decisions(events: Iterable[Mapping]) -> dict[str, int]:
    """Count events by ``event['decision']`` for each recognised decision (§12.3).

    Unknown / missing decision values are ignored (never added to the output dict).
    """
    counts: dict[str, int] = dict.fromkeys(DECISIONS, 0)
    for event in events:
        decision = event.get("decision")
        if decision in counts:
            counts[decision] += 1
    return counts


def corrections_per_100(
    events: Iterable[Mapping], total_extractions: int
) -> ReviewerCorrectionStats:
    """Aggregate curation ``events`` into :class:`ReviewerCorrectionStats`.

    Corrections = rejected + merged + split + corrected (``accepted`` excluded).
    ``corrections_per_100`` = 100 * corrections / total_extractions, or ``0.0`` when
    ``total_extractions`` is 0 (no ZeroDivisionError).
    """
    counts = count_decisions(events)
    corrections = sum(counts[decision] for decision in CORRECTION_DECISIONS)
    per_100 = 100.0 * corrections / total_extractions if total_extractions else 0.0
    return ReviewerCorrectionStats(
        total_extractions=int(total_extractions),
        accepted=counts["accepted"],
        rejected=counts["rejected"],
        merged=counts["merged"],
        split=counts["split"],
        corrected=counts["corrected"],
        corrections_per_100=per_100,
    )
