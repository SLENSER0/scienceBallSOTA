"""Per-slice data-quality scorecards с ранжированием (§23.24).

Pure-stdlib scorecard that ranks slices (lab / material / property) by a
composite quality score and surfaces the worst-N offenders. Дополняет
:mod:`kg_eval.kg_health_score` (единый composite для всего графа) и
отличается от :mod:`kg_eval.quality_gates` (pass/fail пороги): здесь мы
*ранжируем срезы* друг относительно друга, чтобы найти худших.

Each slice is described by a mapping of already-normalized metrics (each in
``0..1``, "выше — лучше"). Композитный балл среза — взвешенное среднее его
метрик, масштабированное в ``0..100``::

    score = 100 * sum(metrics[k] * weights[k]) / sum(weights[k])   # k присутствуют в обоих

Метрика без веса в ``weights`` в подсчёте игнорируется — так частичный набор
весов оценивает срез по своей собственной сумме весов, а не штрафует за
отсутствующие компоненты.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


def slice_score(metrics: Mapping[str, float], *, weights: Mapping[str, float]) -> float:
    """Взвешенное среднее метрик среза, масштабированное в 0..100 (§23.24).

    Учитываются только метрики, у которых есть вес в ``weights``; метрика без
    веса игнорируется. Если ни одна метрика не имеет веса (или сумма весов
    равна нулю), балл — ``0.0``.
    """
    total_weight = 0.0
    weighted = 0.0
    for name, value in metrics.items():
        weight = weights.get(name)
        if weight is None:
            continue
        total_weight += weight
        weighted += value * weight
    if total_weight == 0.0:
        return 0.0
    return 100.0 * weighted / total_weight


@dataclass(frozen=True)
class SliceScore:
    """Композитный балл одного среза (§23.24).

    ``slice_id`` — идентификатор среза (lab/material/property); ``score`` —
    балл 0..100; ``metrics`` — исходные (нормированные 0..1) метрики среза.
    """

    slice_id: str
    score: float
    metrics: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        return {
            "slice_id": self.slice_id,
            "score": round(self.score, 6),
            "metrics": {k: round(v, 6) for k, v in self.metrics.items()},
        }


@dataclass(frozen=True)
class Scorecard:
    """Ранжированный scorecard срезов + худшие N (§23.24).

    ``rows`` — все срезы, отсортированные по ``score`` убыванию (ties по
    ``slice_id`` лексикографически); ``worst`` — ``worst_n`` худших срезов
    (наименьший балл первым); ``mean_score`` — среднее по баллам ``rows``.
    """

    rows: tuple[SliceScore, ...]
    worst: tuple[SliceScore, ...]
    mean_score: float

    def as_dict(self) -> dict[str, object]:
        return {
            "rows": [r.as_dict() for r in self.rows],
            "worst": [r.as_dict() for r in self.worst],
            "mean_score": round(self.mean_score, 6),
        }


def build_scorecard(
    slices: Mapping[str, Mapping[str, float]],
    *,
    weights: Mapping[str, float],
    worst_n: int = 3,
) -> Scorecard:
    """Собрать ранжированный scorecard из метрик срезов (§23.24).

    ``slices`` — отображение ``slice_id -> metrics``; каждый срез оценивается
    через :func:`slice_score`. ``rows`` сортируются по баллу убыванию, ties по
    ``slice_id`` лексикографически. ``worst`` — ``worst_n`` наименьших баллов
    (наименьший первым), длиной ``min(worst_n, len(slices))``.

    Пустой ``slices`` — это ошибка (нечего ранжировать): ``ValueError``.
    """
    if not slices:
        raise ValueError("build_scorecard: 'slices' must be non-empty")

    scored = [
        SliceScore(slice_id=sid, score=slice_score(metrics, weights=weights), metrics=dict(metrics))
        for sid, metrics in slices.items()
    ]
    rows = tuple(sorted(scored, key=lambda s: (-s.score, s.slice_id)))
    mean_score = sum(s.score for s in rows) / len(rows)

    # Худшие: наименьший балл первым (ties по slice_id лексикографически).
    by_worst = sorted(scored, key=lambda s: (s.score, s.slice_id))
    n = max(0, min(worst_n, len(scored)))
    worst = tuple(by_worst[:n])

    return Scorecard(rows=rows, worst=worst, mean_score=mean_score)
