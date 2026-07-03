"""Composite 0–100 KG health score + data-quality scorecard (§23.24).

Pure-stdlib scorer that folds a handful of *already-normalized* component
metrics (each in ``0..1``) into a single interpretable health score, a letter
grade and a pass/fail gate. Некоторые метрики "выше — лучше" (например
``evidence_coverage``), другие "ниже — лучше" (``orphan_rate``,
``duplicate_rate``, ``contradiction_rate``) — последние перечислены в
:data:`LOWER_IS_BETTER` и инвертируются (``1 - raw``) прежде чем взвешиваться,
так что их вклад тоже "выше — лучше".

The score is a weighted mean of the (possibly inverted) component values,
rescaled to ``0..100``::

    score = 100 * sum(contribution) / sum(weight)   # over metrics present

Only the components actually present in ``metrics`` participate, so a partial
scorecard (say only coverage + orphan_rate) is scored against its own weight
sum rather than being penalised for the missing components. A metric key that
is not in ``weights`` raises :class:`KeyError` — unknown metrics are a bug, not
a silently-zero contribution.

Letter grade: ``A >= 90``, ``B >= 75``, ``C >= 60``, ``D >= 40``, else ``F``.
The gate (``gate_passed``) fails when any component's (inverted) value is below
its per-metric threshold; :attr:`HealthScore.failing` names those components.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Метрики, для которых меньшее значение лучше: инвертируются перед взвешиванием.
LOWER_IS_BETTER: frozenset[str] = frozenset(
    {"orphan_rate", "duplicate_rate", "contradiction_rate", "stale_rate"}
)

# Веса компонент по умолчанию (§23.24). Не нормированы — score делит на их сумму.
DEFAULT_WEIGHTS: Mapping[str, float] = {
    "evidence_coverage": 3.0,
    "orphan_rate": 2.0,
    "duplicate_rate": 2.0,
    "contradiction_rate": 3.0,
    "stale_rate": 1.0,
}


@dataclass(frozen=True)
class Component:
    """Один компонент health-score после инверсии/взвешивания (§23.24).

    ``raw`` — исходное значение метрики (0..1) до инверсии; ``contribution`` —
    вклад ``effective * weight`` (для lower-is-better ``effective = 1 - raw``);
    ``healthy`` — прошёл ли компонент свой порог.
    """

    name: str
    raw: float
    weight: float
    contribution: float
    healthy: bool

    def as_dict(self) -> dict[str, float | str | bool]:
        return {
            "name": self.name,
            "raw": round(self.raw, 6),
            "weight": round(self.weight, 6),
            "contribution": round(self.contribution, 6),
            "healthy": self.healthy,
        }


@dataclass(frozen=True)
class HealthScore:
    """Aggregate KG health verdict (§23.24).

    ``score`` — 0..100; ``grade`` — буква A..F; ``components`` — покомпонентная
    разбивка; ``gate_passed`` — все ли компоненты прошли пороги; ``failing`` —
    имена компонент ниже порога (в порядке следования в ``metrics``).
    """

    score: float
    grade: str
    components: tuple[Component, ...]
    gate_passed: bool
    failing: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "score": round(self.score, 4),
            "grade": self.grade,
            "components": [c.as_dict() for c in self.components],
            "gate_passed": self.gate_passed,
            "failing": list(self.failing),
        }


def _effective(name: str, raw: float) -> float:
    """Значение "выше — лучше": инвертирует raw для lower-is-better метрик."""
    return (1.0 - raw) if name in LOWER_IS_BETTER else raw


def component_contribution(name: str, raw: float, weight: float) -> float:
    """Взвешенный вклад компонента (raw инвертируется для lower-is-better)."""
    return _effective(name, raw) * weight


def _grade(score: float) -> str:
    """Буквенная оценка по score (границы включительно: 90/75/60/40)."""
    if score >= 90.0:
        return "A"
    if score >= 75.0:
        return "B"
    if score >= 60.0:
        return "C"
    if score >= 40.0:
        return "D"
    return "F"


def kg_health_score(
    metrics: Mapping[str, float],
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
    thresholds: Mapping[str, float] | None = None,
) -> HealthScore:
    """Свернуть покомпонентные метрики в composite health-score (§23.24).

    ``metrics`` — ``{name: raw}`` с ``raw`` в ``0..1``. Каждый ``name`` обязан
    присутствовать в ``weights`` (иначе :class:`KeyError`). Порог для компонента
    берётся из ``thresholds`` (если задан) и сравнивается с "выше — лучше"
    значением; при отсутствии порога компонент считается прошедшим.
    """
    thr = thresholds or {}
    components: list[Component] = []
    failing: list[str] = []
    total_weight = 0.0
    total_contribution = 0.0

    for name, raw in metrics.items():
        weight = weights[name]  # KeyError на неизвестной метрике — это баг.
        contribution = component_contribution(name, raw, weight)
        effective = _effective(name, raw)
        limit = thr.get(name)
        healthy = True if limit is None else effective >= limit
        if not healthy:
            failing.append(name)
        components.append(Component(name, raw, weight, contribution, healthy))
        total_weight += weight
        total_contribution += contribution

    raw_score = 100.0 * total_contribution / total_weight if total_weight else 0.0
    score = max(0.0, min(100.0, raw_score))
    return HealthScore(
        score=score,
        grade=_grade(score),
        components=tuple(components),
        gate_passed=not failing,
        failing=tuple(failing),
    )
