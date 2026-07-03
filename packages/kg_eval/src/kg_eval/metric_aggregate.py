"""Aggregate per-metric statistics across repeated eval runs (§18.12).

Pure, deterministic, dependency-free reduction of a list of run dicts into a
``{mean, std, min, max, n}`` summary *per metric key*. Used to collapse several
repetitions of the same evaluation (§18: прогоны на одном golden-наборе) into a
single stability report — how большой разброс a metric has across runs.

Each *run* is a flat ``dict[str, float]`` mapping metric key -> value. Keys need
not be present in every run: a key is aggregated only over the runs that actually
contain it, and ``n`` records how many contributed. A key absent from every run
never appears in the output; ``aggregate_metrics([])`` returns an empty mapping.

``std`` is the *population* standard deviation (divide by ``n``, not ``n - 1``),
so a metric observed in a single run has ``std == 0.0`` rather than an undefined
sample variance. ``mean``/``std`` are floats; ``min``/``max`` preserve the exact
observed values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class MetricAggregate:
    """Summary statistics for one metric key across runs (§18.12).

    ``n`` is the number of runs that contained the key; ``mean`` и ``std`` are
    floats (population std), ``min``/``max`` are the exact extreme values.
    """

    mean: float
    std: float
    min: float
    max: float
    n: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "mean": round(self.mean, 6),
            "std": round(self.std, 6),
            "min": self.min,
            "max": self.max,
            "n": self.n,
        }


def _aggregate_values(values: Sequence[float]) -> MetricAggregate:
    """Reduce a non-empty sequence of one metric's values into a summary."""
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return MetricAggregate(
        mean=mean,
        std=sqrt(variance),
        min=min(values),
        max=max(values),
        n=n,
    )


def aggregate_metrics(runs: list[dict[str, float]]) -> dict[str, MetricAggregate]:
    """Aggregate each metric key over ``runs`` into a :class:`MetricAggregate`.

    A key is summarised only across the runs that contain it; keys absent from
    every run are omitted and ``n`` counts the contributing runs. An empty
    ``runs`` list yields an empty mapping.
    """
    collected: dict[str, list[float]] = {}
    for run in runs:
        for key, value in run.items():
            collected.setdefault(key, []).append(value)
    return {key: _aggregate_values(values) for key, values in collected.items()}
