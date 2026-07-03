"""Per-slice KG health breakdown (§23.24).

:mod:`kg_eval.kg_health_score` folds one component-metric bag into a single
composite verdict. §23.24 additionally требует *score по срезам* — health
считается отдельно для каждого среза (lab / material family / property /
source type), чтобы видеть, где именно граф "болеет", а не только усреднённое
здоровье по всему KG.

Вход — ``Mapping[slice_name, component_metrics]``, где ``component_metrics`` —
тот же ``{name: raw}`` (каждый ``raw`` в ``0..1``), что потребляет
:func:`kg_eval.kg_health_score.kg_health_score`. Каждый срез скорится этой же
функцией (общие веса/пороги), поэтому буквенные оценки и логика гейта
наследуются один-в-один.

:func:`breakdown` возвращает :class:`SliceBreakdownReport`:

* ``mean_score`` — арифметическое среднее slice-скорингов;
* ``worst`` — имена ``worst_k`` худших срезов (по возрастанию score, ties
  разрешаются по алфавиту);
* ``all_gates_passed`` — прошёл ли гейт *каждый* срез;
* ``slices`` — :class:`SliceHealth` по одному на срез, отсортированы по имени.

Пустой вход — ошибка (:class:`ValueError`): усреднять/ранжировать нечего.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kg_eval.kg_health_score import DEFAULT_WEIGHTS, kg_health_score


@dataclass(frozen=True)
class SliceHealth:
    """Health-вердикт одного среза (§23.24).

    ``slice`` — имя среза; ``score`` — 0..100; ``grade`` — буква A..F;
    ``gate_passed`` — прошли ли все компоненты среза свои пороги. Значения
    ``score``/``grade``/``gate_passed`` берутся из
    :func:`kg_eval.kg_health_score.kg_health_score` для этого среза.
    """

    slice: str
    score: float
    grade: str
    gate_passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "slice": self.slice,
            "score": round(self.score, 4),
            "grade": self.grade,
            "gate_passed": self.gate_passed,
        }


@dataclass(frozen=True)
class SliceBreakdownReport:
    """Сводка health по всем срезам (§23.24).

    ``n`` — число срезов; ``mean_score`` — среднее их скорингов; ``worst`` —
    имена худших срезов (по возрастанию score, ties по алфавиту); ``all_gates_
    passed`` — прошёл ли гейт каждый срез; ``slices`` — :class:`SliceHealth`,
    отсортированы по имени среза.
    """

    n: int
    mean_score: float
    worst: tuple[str, ...]
    all_gates_passed: bool
    slices: tuple[SliceHealth, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "mean_score": round(self.mean_score, 4),
            "worst": list(self.worst),
            "all_gates_passed": self.all_gates_passed,
            "slices": [s.as_dict() for s in self.slices],
        }


def breakdown(
    slices: Mapping[str, Mapping[str, float]],
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
    thresholds: Mapping[str, float] | None = None,
    worst_k: int = 3,
) -> SliceBreakdownReport:
    """Посчитать health по каждому срезу и свести в отчёт (§23.24).

    ``slices`` — ``{slice_name: {metric: raw}}``. Каждый срез скорится
    :func:`kg_eval.kg_health_score.kg_health_score` с общими ``weights`` и
    ``thresholds``. ``worst_k`` ограничивает длину списка ``worst`` (худшие
    срезы по возрастанию score, ties по алфавиту). Пустой ``slices`` —
    :class:`ValueError`.
    """
    if not slices:
        raise ValueError("slices is empty: nothing to break down")
    if worst_k < 0:
        raise ValueError(f"worst_k must be non-negative, got {worst_k}")

    healths: list[SliceHealth] = []
    for name in sorted(slices):
        hs = kg_health_score(slices[name], weights=weights, thresholds=thresholds)
        healths.append(SliceHealth(name, hs.score, hs.grade, hs.gate_passed))

    mean_score = sum(h.score for h in healths) / len(healths)
    ranked = sorted(healths, key=lambda h: (h.score, h.slice))
    worst = tuple(h.slice for h in ranked[:worst_k])
    all_gates_passed = all(h.gate_passed for h in healths)

    return SliceBreakdownReport(
        n=len(healths),
        mean_score=mean_score,
        worst=worst,
        all_gates_passed=all_gates_passed,
        slices=tuple(healths),
    )
