"""Eval quality gates + regression thresholds (§18.8).

Пороговые «ворота качества» для оценочных метрик и детектор регрессий между
прогонами. Метрики — «чем больше, тем лучше» (recall/mrr/f1/grounding), поэтому
каждое значение сверяется с порогом через ``>=``. :func:`check_gates` собирает
:class:`GateReport` (прошло/провалы/подробности по каждой метрике);
:func:`is_regression` возвращает метрики, просевшие относительно эталона больше,
чем на допуск ``tol``.

Quality gates for eval metrics: :func:`check_gates` compares a metrics dict against
per-metric thresholds (``>=``, higher-is-better) and reports a frozen
:class:`GateReport`; :func:`is_regression` lists metrics that dropped from a
baseline by more than ``tol``.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Default regression thresholds (higher-is-better score metrics; compared with ``>=``).
# Пороги по умолчанию: минимально допустимое значение каждой метрики (§18.8).
DEFAULT_GATES: dict[str, float] = {
    "recall_at_5": 0.6,
    "mrr": 0.5,
    "extraction_f1": 0.7,
    "answer_grounding": 0.9,
}

# Rounding applied to a computed drop before the ``> tol`` test — guards against
# float noise (e.g. ``0.6 - 0.58 == 0.020000000000000018``) at the tolerance edge.
_DROP_NDIGITS = 9

# Reason codes attached to a failing gate.
_BELOW = "below_threshold"  # metric present but ``actual < threshold``
_MISSING = "missing"  # metric absent from the supplied metrics dict


@dataclass(frozen=True)
class GateFailure:
    """One failed gate — метрика, факт, порог и причина провала (§18.8).

    ``actual`` is ``None`` when the metric was missing from the metrics dict
    (``reason == "missing"``); otherwise it is the observed value that fell below
    ``threshold`` (``reason == "below_threshold"``).
    """

    metric: str
    actual: float | None
    threshold: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "metric": self.metric,
            "actual": self.actual,
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GateReport:
    """Result of a gate check — прошло ли, список провалов, статус по метрикам (§18.8).

    ``checked`` maps every gate metric to a boolean (did it pass); ``failures`` holds
    a :class:`GateFailure` per failing metric; ``passed`` is ``True`` iff there are no
    failures.
    """

    passed: bool
    failures: tuple[GateFailure, ...]
    checked: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); ``failures`` become a list of dicts."""
        return {
            "passed": self.passed,
            "failures": [f.as_dict() for f in self.failures],
            "checked": dict(self.checked),
        }


def check_gates(
    metrics: Mapping[str, float],
    *,
    gates: Mapping[str, float] | None = None,
) -> GateReport:
    """Compare ``metrics`` against ``gates`` (``>=`` per metric) → :class:`GateReport`.

    Сверяет каждую метрику из ``gates`` (по умолчанию :data:`DEFAULT_GATES`) с её
    порогом: метрика проходит, если ``actual >= threshold``. Отсутствующая метрика
    считается провалом с причиной ``"missing"`` (нельзя подтвердить, что ворота
    пройдены). Лишние метрики во входном словаре игнорируются.

    Only gate metrics are inspected; a metric missing from ``metrics`` (or present as
    ``None``) fails with reason ``"missing"``. ``passed`` is ``True`` iff ``failures``
    is empty.
    """
    active = DEFAULT_GATES if gates is None else gates
    failures: list[GateFailure] = []
    checked: dict[str, bool] = {}
    for metric, threshold in active.items():
        actual = metrics.get(metric)
        if actual is None:
            checked[metric] = False
            failures.append(GateFailure(metric, None, float(threshold), _MISSING))
            continue
        ok = float(actual) >= float(threshold)
        checked[metric] = ok
        if not ok:
            failures.append(GateFailure(metric, float(actual), float(threshold), _BELOW))
    return GateReport(passed=not failures, failures=tuple(failures), checked=checked)


def is_regression(
    current: Mapping[str, float],
    baseline: Mapping[str, float],
    *,
    tol: float = 0.02,
) -> list[str]:
    """List metrics that dropped from ``baseline`` to ``current`` by more than ``tol``.

    Считает регрессией просадку ``baseline[m] - current[m] > tol`` (строго больше —
    просадка ровно на ``tol`` в допуске). Метрики, отсутствующие в ``current``,
    пропускаются. Улучшения (отрицательная разность) регрессией не являются.
    Результат отсортирован для детерминизма.

    A drop is compared strictly (``> tol``); a drop of exactly ``tol`` is within
    tolerance. Metrics absent from ``current`` are skipped. Returns the regressed
    metric names, sorted.
    """
    regressed: list[str] = []
    for metric, base_value in baseline.items():
        cur = current.get(metric)
        if cur is None:
            continue
        drop = round(float(base_value) - float(cur), _DROP_NDIGITS)
        if drop > tol:
            regressed.append(metric)
    return sorted(regressed)
