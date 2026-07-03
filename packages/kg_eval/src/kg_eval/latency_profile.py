"""Latency percentile profiler + SLO gating (§23.9 Производительность и нагрузочное тестирование).

Pure-stdlib profiler for load-test latency sample lists. Computes summary
statistics (mean / p50 / p95 / p99 / min / max) via nearest-rank percentiles and
gates a run against a service-level objective (SLO) threshold.

Distinct from ``telemetry.py`` (which *records* live events) — this module
*analyses* an already-collected list of latency samples offline.

Латентность и нагрузочное тестирование: перцентили по методу ближайшего ранга.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyProfile:
    """Summary of a latency sample distribution (all values in caller's units, e.g. ms)."""

    n: int
    mean: float
    p50: float
    p95: float
    p99: float
    max: float
    min: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "mean": round(self.mean, 4),
            "p50": round(self.p50, 4),
            "p95": round(self.p95, 4),
            "p99": round(self.p99, 4),
            "max": round(self.max, 4),
            "min": round(self.min, 4),
        }


@dataclass(frozen=True)
class SLOCheck:
    """Result of gating one profile metric against an SLO threshold."""

    passed: bool
    metric: str
    threshold: float
    observed: float

    def as_dict(self) -> dict[str, bool | str | float]:
        return {
            "passed": self.passed,
            "metric": self.metric,
            "threshold": round(self.threshold, 4),
            "observed": round(self.observed, 4),
        }


def percentile(samples: Sequence[float], q: float) -> float:
    """Nearest-rank percentile of ``samples`` for ``q`` in [0, 100].

    Sorts the values and picks rank ``ceil(q/100 * n)`` (1-indexed), so ``q=0``
    returns the minimum and ``q=100`` returns the maximum.
    """
    if not samples:
        raise ValueError("percentile() requires at least one sample")
    if not 0.0 <= q <= 100.0:
        raise ValueError(f"q must be in [0, 100], got {q!r}")
    ordered = sorted(samples)
    n = len(ordered)
    if q == 0.0:
        return float(ordered[0])
    # Nearest-rank: rank = ceil(q/100 * n), 1-indexed → clamp into [1, n].
    rank = -(-round(q * n) // 100)  # ceil(q*n/100) without float drift
    rank = max(1, min(rank, n))
    return float(ordered[rank - 1])


def profile(samples: Sequence[float]) -> LatencyProfile:
    """Compute a :class:`LatencyProfile` over non-empty ``samples``."""
    if not samples:
        raise ValueError("profile() requires at least one sample")
    ordered = sorted(float(s) for s in samples)
    n = len(ordered)
    mean = sum(ordered) / n
    return LatencyProfile(
        n=n,
        mean=mean,
        p50=percentile(ordered, 50.0),
        p95=percentile(ordered, 95.0),
        p99=percentile(ordered, 99.0),
        max=ordered[-1],
        min=ordered[0],
    )


def check_slo(profile: LatencyProfile, *, metric: str = "p95", threshold_ms: float) -> SLOCheck:
    """Gate one metric of ``profile`` against ``threshold_ms`` (passed if observed <= threshold)."""
    allowed = {"mean", "p50", "p95", "p99", "max", "min"}
    if metric not in allowed:
        raise ValueError(f"unknown metric {metric!r}; expected one of {sorted(allowed)}")
    observed = float(getattr(profile, metric))
    return SLOCheck(
        passed=observed <= threshold_ms,
        metric=metric,
        threshold=float(threshold_ms),
        observed=observed,
    )
