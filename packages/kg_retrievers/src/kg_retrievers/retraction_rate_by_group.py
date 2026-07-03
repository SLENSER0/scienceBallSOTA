"""Per-group retraction (contamination) rate — доля ретракций по группам (§25.12).

:mod:`kg_retrievers.retraction_report` gives one *global* retracted share plus a
reason histogram. That is blind to *where* the contamination sits: a single
domain, property, or source can be quietly rotten while the overall number looks
fine. This module slices the same observations by a chosen key (``domain`` /
``property`` / ``source``) and reports a retraction *rate* per bucket, plus the
worst offenders.

An observation is "retracted" iff its ``retracted`` prop is truthy (per §25.12 the
tombstone lives in the JSON ``props`` catch-all, flattened here at the top level).
Observations missing ``group_key`` fall under the em-dash bucket ``'—'`` (группа
не указана).

Pure Python and read-only: reads no store and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Bucket for an observation whose ``group_key`` is missing (группа не указана).
MISSING_GROUP = "—"


@dataclass(frozen=True)
class GroupRetractionRate:
    """Retraction rate for one group: n observations, n_retracted, rate (§25.12).

    ``rate`` is ``n_retracted / n`` (``n`` is always > 0 for a materialized group).
    """

    group: str
    n: int
    n_retracted: int
    rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "n": self.n,
            "n_retracted": self.n_retracted,
            "rate": self.rate,
        }


@dataclass(frozen=True)
class RetractionRateReport:
    """Per-group contamination report: every group, overall rate, worst offenders (§25.12).

    ``groups`` holds one :class:`GroupRetractionRate` per bucket (group-sorted).
    ``overall_rate`` is ``total_retracted / total`` — ``0.0`` on empty input.
    ``worst`` is ``groups`` sorted by rate desc then group asc, capped at ``top_n``.
    """

    groups: tuple[GroupRetractionRate, ...]
    overall_rate: float
    worst: tuple[GroupRetractionRate, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "groups": [g.as_dict() for g in self.groups],
            "overall_rate": self.overall_rate,
            "worst": [g.as_dict() for g in self.worst],
        }


def retraction_rate_by_group(
    observations: list[dict],
    *,
    group_key: str = "domain",
    top_n: int = 5,
) -> RetractionRateReport:
    """Compute the retraction rate of ``observations`` grouped by ``group_key`` (§25.12).

    Observations are bucketed by their ``group_key`` value (missing → :data:`MISSING_GROUP`).
    Per bucket, ``rate = n_retracted / n`` where retracted means a truthy ``retracted``
    prop. ``overall_rate`` is ``total_retracted / total`` (``0.0`` when empty). ``worst``
    ranks buckets by rate descending, ties broken by group name ascending, capped at
    ``top_n``.
    """
    counts: dict[str, list[int]] = {}  # group -> [n, n_retracted]
    total = 0
    total_retracted = 0
    for obs in observations:
        raw = obs.get(group_key)
        group = MISSING_GROUP if raw is None else str(raw)
        retracted = 1 if obs.get("retracted") else 0
        bucket = counts.setdefault(group, [0, 0])
        bucket[0] += 1
        bucket[1] += retracted
        total += 1
        total_retracted += retracted

    groups = tuple(
        GroupRetractionRate(group=g, n=n, n_retracted=nr, rate=nr / n)
        for g, (n, nr) in sorted(counts.items())
    )
    worst = tuple(sorted(groups, key=lambda g: (-g.rate, g.group))[:top_n])
    overall_rate = total_retracted / total if total else 0.0

    return RetractionRateReport(groups=groups, overall_rate=overall_rate, worst=worst)
