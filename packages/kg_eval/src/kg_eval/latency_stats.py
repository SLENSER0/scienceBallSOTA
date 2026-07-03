"""Latency percentile summary for chat/graph-query samples (§18.5).

Pure-python percentile histograms (p50/p95/p99) over latency samples in
milliseconds. Complements ``metric_aggregate.py`` (which only computes
mean/std/min/max) by reporting the *tail* of the distribution — §18.5
требует p50/p95/p99 гистограммы для ``chat_latency`` и ``graph_query_latency``.

``percentile`` uses linear interpolation between the two nearest ranks (the
same convention as ``numpy.percentile`` default / statistics.quantiles), with
``q`` expressed as a fraction in ``[0, 1]``. ``summarize_latencies`` collapses
an iterable of samples into a frozen :class:`LatencySummary`, optionally
counting SLO violations (samples strictly greater than ``slo_ms``).

Empty input is well-defined: ``count == 0`` and every percentile / mean / max is
``0.0`` (no exception), so callers can render a summary before any traffic.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencySummary:
    """Percentile summary of latency samples in milliseconds (§18.5).

    ``count`` — number of samples; ``p50``/``p95``/``p99`` — interpolated
    percentiles; ``mean``/``max`` — среднее и максимум; ``slo_ms`` — целевой
    SLO (или ``None``); ``slo_violations`` — сколько samples > ``slo_ms``.
    """

    count: int
    p50: float
    p95: float
    p99: float
    mean: float
    max: float
    slo_ms: float | None
    slo_violations: int

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "count": int(self.count),
            "p50": round(self.p50, 6),
            "p95": round(self.p95, 6),
            "p99": round(self.p99, 6),
            "mean": round(self.mean, 6),
            "max": round(self.max, 6),
            "slo_ms": self.slo_ms,
            "slo_violations": int(self.slo_violations),
        }


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Return the ``q``-th percentile (``q`` in ``[0, 1]``) via linear interp.

    ``sorted_values`` must be sorted ascending. Uses the ``(n - 1) * q`` rank
    with linear interpolation between neighbours. Empty input returns ``0.0``;
    a single-element sequence returns that element for any ``q``.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q!r}")
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_values[0])
    rank = (n - 1) * q
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_values[lo]) + (float(sorted_values[hi]) - float(sorted_values[lo])) * frac


def summarize_latencies(
    samples_ms: Iterable[float],
    slo_ms: float | None = None,
) -> LatencySummary:
    """Summarize latency samples (ms) into a :class:`LatencySummary` (§18.5).

    ``slo_violations`` counts samples strictly greater than ``slo_ms``; it is
    ``0`` when ``slo_ms`` is ``None``. Empty input yields a zeroed summary.
    """
    values = sorted(float(s) for s in samples_ms)
    count = len(values)
    if count == 0:
        return LatencySummary(
            count=0,
            p50=0.0,
            p95=0.0,
            p99=0.0,
            mean=0.0,
            max=0.0,
            slo_ms=slo_ms,
            slo_violations=0,
        )
    violations = 0 if slo_ms is None else sum(1 for v in values if v > slo_ms)
    return LatencySummary(
        count=count,
        p50=percentile(values, 0.50),
        p95=percentile(values, 0.95),
        p99=percentile(values, 0.99),
        mean=sum(values) / count,
        max=values[-1],
        slo_ms=slo_ms,
        slo_violations=violations,
    )
