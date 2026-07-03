"""Leave-one-out ablation contribution matrix (§23.31/§23.19).

Оценивает вклад каждого компонента пайплайна методом «выбрасывания по одному»
(leave-one-out): счёт полной системы сравнивается со счётом системы, из которой
удалён ровно один компонент (флаги ``without-reranker`` /
``without-graph_proximity`` / ``without-verifier`` из §23.19). Вклад компонента —
это разница «полный минус абляция», нормализованная по знаку так, что
положительное значение всегда означает «компонент помогает» (для метрик, где
меньше — лучше, знак инвертируется). Компоненты сортируются по вкладу по убыванию,
самый важный — с максимальным вкладом.

Это НЕ :mod:`baseline_benchmark` (там ранжируются целые системы-конкуренты):
здесь изолируется leave-one-out дельта одного компонента и ранжируются компоненты.

Leave-one-out ablation: each component's marginal contribution is the full-system
score minus the score with that single component ablated, sign-adjusted so a
positive value always means the component helps (sign flips when lower is better).
Components are ranked by contribution descending; the most important has the
largest contribution. Distinct from :mod:`baseline_benchmark`, which ranks whole
rival systems — here a single component's leave-one-out delta is isolated.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Округление вклада перед сортировкой/сравнением — гасит float-шум у нуля
# (напр. ``0.9 - 0.85 == 0.04999999999999982``).
# Rounding applied to the contribution — guards against float noise near zero.
_CONTRIB_NDIGITS = 12


@dataclass(frozen=True)
class ComponentContribution:
    """Вклад одного компонента при leave-one-out абляции (§23.19).

    ``ablated_score`` — счёт системы без этого компонента. ``contribution`` —
    нормализованная по знаку дельта «полный минус абляция»: положительное
    значение означает, что компонент помогает; ноль — не влияет; отрицательное —
    вредит (абляция оказалась лучше полной системы).

    ``ablated_score`` is the score with this component removed. ``contribution``
    is the sign-adjusted full-minus-ablated delta: positive means the component
    helps, zero means no effect, negative means it hurts.
    """

    component: str
    ablated_score: float
    contribution: float

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "component": self.component,
            "ablated_score": self.ablated_score,
            "contribution": self.contribution,
        }


@dataclass(frozen=True)
class AblationReport:
    """Матрица вкладов компонентов, отсортированная по убыванию (§23.31/§23.19).

    ``components`` упорядочены по ``contribution`` по убыванию (ничьи — по имени
    компонента для детерминизма). ``most_important`` — имя компонента с
    наибольшим вкладом либо ``None``, если абляций не было.

    ``components`` are sorted by ``contribution`` descending (ties broken by
    component name). ``most_important`` is the top component's name, or ``None``
    when no ablations were supplied.
    """

    full_score: float
    higher_is_better: bool
    components: tuple[ComponentContribution, ...]
    most_important: str | None

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); ``components`` becomes a list of dicts."""
        return {
            "full_score": self.full_score,
            "higher_is_better": self.higher_is_better,
            "components": [c.as_dict() for c in self.components],
            "most_important": self.most_important,
        }


def analyze(
    full_score: float,
    ablated: Mapping[str, float],
    higher_is_better: bool = True,
) -> AblationReport:
    """Построить :class:`AblationReport` из счёта абляций (§23.31/§23.19).

    Для каждого компонента ``contribution = sign * (full_score - ablated_score)``,
    где ``sign`` равен ``+1`` при ``higher_is_better`` иначе ``-1``. Тем самым
    положительный вклад всегда означает «компонент помогает». Компоненты
    сортируются по вкладу по убыванию (ничьи — по имени). ``most_important`` —
    имя первого компонента либо ``None`` для пустого ``ablated``.

    For each component ``contribution = sign * (full_score - ablated_score)`` with
    ``sign`` ``+1`` when ``higher_is_better`` else ``-1``, so a positive value
    always means the component helps. Components are sorted by contribution
    descending (ties by name); ``most_important`` is the top name or ``None`` for
    an empty ``ablated`` mapping.
    """
    full = float(full_score)
    sign = 1.0 if higher_is_better else -1.0
    rows: list[ComponentContribution] = []
    for component in ablated:
        ablated_score = float(ablated[component])
        contribution = round(sign * (full - ablated_score), _CONTRIB_NDIGITS)
        rows.append(
            ComponentContribution(
                component=component,
                ablated_score=ablated_score,
                contribution=contribution,
            )
        )
    # Убывание по вкладу; ничьи разрешаются по имени для детерминизма.
    # Descending by contribution; ties broken by component name.
    rows.sort(key=lambda r: (-r.contribution, r.component))
    most_important = rows[0].component if rows else None
    return AblationReport(
        full_score=full,
        higher_is_better=bool(higher_is_better),
        components=tuple(rows),
        most_important=most_important,
    )
