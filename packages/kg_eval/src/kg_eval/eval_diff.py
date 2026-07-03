"""Eval run-to-run diff: improved / regressed / unchanged metrics (§18.13).

Сравнение двух прогонов метрик оценки («эталон» vs «текущий»). Метрики —
«чем больше, тем лучше», поэтому дельта считается как ``current - baseline``:
рост выше допуска ``tol`` — улучшение, падение ниже ``-tol`` — регрессия, всё
между — без изменений. :func:`eval_diff` собирает замороженный :class:`EvalDiff`
со списками :class:`MetricDelta` и вердиктом ``"pass"``/``"fail"`` (``"fail"``,
если есть хотя бы одна регрессия). Метрики, отсутствующие в одном из словарей,
пропускаются — как и в :func:`quality_gates.is_regression`.

Run-to-run diff of eval metrics. Deltas are ``current - baseline`` (higher is
better): a rise above ``tol`` is an improvement, a drop below ``-tol`` a
regression, everything else is unchanged. :func:`eval_diff` returns a frozen
:class:`EvalDiff` whose ``verdict`` is ``"fail"`` iff any metric regressed.
Metrics missing from either dict are skipped.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Rounding applied to a delta before the ``> tol`` test — guards against float
# noise (e.g. ``0.62 - 0.6 == 0.020000000000000018``) at the tolerance edge.
_DELTA_NDIGITS = 9

_PASS = "pass"
_FAIL = "fail"


@dataclass(frozen=True)
class MetricDelta:
    """One metric compared across runs — эталон, текущее, дельта (§18.13).

    ``delta`` is ``current - baseline`` (rounded), so positive means the metric
    improved (higher-is-better).
    """

    metric: str
    baseline: float
    current: float
    delta: float

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "metric": self.metric,
            "baseline": self.baseline,
            "current": self.current,
            "delta": self.delta,
        }


@dataclass(frozen=True)
class EvalDiff:
    """Run-to-run diff — что улучшилось, просело, не изменилось, и вердикт (§18.13).

    ``verdict`` is ``"fail"`` iff ``regressed`` is non-empty, else ``"pass"``.
    Each bucket is sorted by metric name for determinism.
    """

    improved: tuple[MetricDelta, ...]
    regressed: tuple[MetricDelta, ...]
    unchanged: tuple[MetricDelta, ...]
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); each bucket becomes a list of dicts."""
        return {
            "improved": [d.as_dict() for d in self.improved],
            "regressed": [d.as_dict() for d in self.regressed],
            "unchanged": [d.as_dict() for d in self.unchanged],
            "verdict": self.verdict,
        }


def eval_diff(
    baseline: Mapping[str, float],
    current: Mapping[str, float],
    *,
    tol: float = 0.02,
) -> EvalDiff:
    """Diff ``current`` against ``baseline`` → :class:`EvalDiff` (§18.13).

    Для каждой метрики, присутствующей в обоих словарях, считается
    ``delta = current - baseline``: ``delta > tol`` — улучшение, ``delta < -tol`` —
    регрессия, иначе — без изменений (граница ровно ``±tol`` считается «без
    изменений»). Метрики, отсутствующие в одном из словарей, пропускаются.
    Вердикт — ``"fail"``, если есть регрессии, иначе ``"pass"``.

    Only metrics present in *both* dicts are compared; a metric missing from
    either side is skipped. Boundaries are inclusive-unchanged: a delta of exactly
    ``+tol`` or ``-tol`` counts as unchanged (comparison is strict ``>``).
    """
    improved: list[MetricDelta] = []
    regressed: list[MetricDelta] = []
    unchanged: list[MetricDelta] = []
    for metric in baseline:
        cur = current.get(metric)
        if cur is None or metric not in current:
            continue
        base = float(baseline[metric])
        cur = float(cur)
        delta = round(cur - base, _DELTA_NDIGITS)
        item = MetricDelta(metric, base, cur, delta)
        if delta > tol:
            improved.append(item)
        elif delta < -tol:
            regressed.append(item)
        else:
            unchanged.append(item)
    return EvalDiff(
        improved=tuple(sorted(improved, key=_by_metric)),
        regressed=tuple(sorted(regressed, key=_by_metric)),
        unchanged=tuple(sorted(unchanged, key=_by_metric)),
        verdict=_FAIL if regressed else _PASS,
    )


def _by_metric(delta: MetricDelta) -> str:
    """Sort key — metric name (детерминированный порядок в бакетах)."""
    return delta.metric
