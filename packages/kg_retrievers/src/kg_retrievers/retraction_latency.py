"""Time-to-retraction latency over observations — латентность ретракции (§25.12).

Distinct from :mod:`kg_retrievers.retraction_report` (counts + a histogram of
*why* things were withdrawn) and :mod:`kg_retrievers.retraction_impact`
(evidence collapse — *what* a retraction takes down with it): this module
measures *how long* a claim stood before it was retracted — the delay between
its publication date and its retraction date (время до ретракции).

Only nodes carrying a truthy ``retracted`` tombstone count in ``n_retracted``.
For those that also carry both an ISO ``published_at`` and ``retracted_at``, we
compute the latency in days (``retracted - published``) and bucket it into four
coarse bands: ``<=30``, ``31-180``, ``181-365`` and ``>365`` days. A retracted
node missing either date still counts in ``n_retracted`` but contributes no
latency (and is not counted in ``n_with_dates``).

Per §25.12 the ``retracted`` tombstone and its dates live in the JSON ``props``
catch-all rather than queryable Kuzu columns, so callers flatten them onto the
top level of each dict before handing them here.

Pure Python and read-only: it reads no store and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Any

# Bucket labels — ordered coarsest-last (границы корзин латентности, дни).
_BUCKET_LABELS = ("<=30", "31-180", "181-365", ">365")


def _empty_buckets() -> dict[str, int]:
    """A zeroed bucket histogram — все корзины по нулю."""
    return dict.fromkeys(_BUCKET_LABELS, 0)


def _bucket_for(days: float) -> str:
    """Map a latency in days to its bucket label (§25.12)."""
    if days <= 30:
        return "<=30"
    if days <= 180:
        return "31-180"
    if days <= 365:
        return "181-365"
    return ">365"


@dataclass(frozen=True)
class RetractionLatencyReport:
    """Time-to-retraction summary: how long claims stood before withdrawal (§25.12).

    ``n_retracted`` counts every observation with a truthy ``retracted`` prop;
    ``n_with_dates`` is the subset that also had both parseable dates and thus a
    latency. ``latencies_days`` holds those latencies (in input order). The
    ``*_days`` stats are ``None`` when no latency was computed; ``buckets`` is a
    four-band histogram whose counts sum to ``n_with_dates``.
    """

    n_retracted: int
    n_with_dates: int
    latencies_days: tuple[float, ...]
    min_days: float | None
    median_days: float | None
    mean_days: float | None
    max_days: float | None
    buckets: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_retracted": self.n_retracted,
            "n_with_dates": self.n_with_dates,
            "latencies_days": list(self.latencies_days),
            "min_days": self.min_days,
            "median_days": self.median_days,
            "mean_days": self.mean_days,
            "max_days": self.max_days,
            "buckets": dict(self.buckets),
        }


def _days_between(a: str, b: str) -> float | None:
    """Days from ISO date ``a`` to ISO date ``b`` — ``None`` if missing/reversed (§25.12).

    Both ``a`` (published) and ``b`` (retracted) are ISO-8601 strings. Returns
    ``(b - a)`` in whole days as a float, or ``None`` when either is falsy, fails
    to parse, or the retraction predates the publication (reversed — некорректно).
    """
    if not a or not b:
        return None
    try:
        start = datetime.fromisoformat(a)
        end = datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return None
    delta = (end - start).total_seconds() / 86400.0
    if delta < 0:
        return None
    return delta


def retraction_latency(
    observations: list[dict[str, Any]],
    *,
    published_key: str = "published_at",
    retracted_key: str = "retracted_at",
) -> RetractionLatencyReport:
    """Summarize time-to-retraction over ``observations`` (§25.12).

    A node counts in ``n_retracted`` iff its ``retracted`` prop is truthy. For
    each such node we read ``published_key``/``retracted_key`` and, when both
    parse to a non-reversed interval, record the latency in days and bucket it.
    """
    n_retracted = 0
    latencies: list[float] = []
    buckets = _empty_buckets()

    for obs in observations:
        if not obs.get("retracted"):
            continue
        n_retracted += 1
        days = _days_between(obs.get(published_key, ""), obs.get(retracted_key, ""))
        if days is None:
            continue
        latencies.append(days)
        buckets[_bucket_for(days)] += 1

    if latencies:
        min_days: float | None = min(latencies)
        max_days: float | None = max(latencies)
        mean_days: float | None = float(mean(latencies))
        median_days: float | None = float(median(latencies))
    else:
        min_days = max_days = mean_days = median_days = None

    return RetractionLatencyReport(
        n_retracted=n_retracted,
        n_with_dates=len(latencies),
        latencies_days=tuple(latencies),
        min_days=min_days,
        median_days=median_days,
        mean_days=mean_days,
        max_days=max_days,
        buckets=buckets,
    )
