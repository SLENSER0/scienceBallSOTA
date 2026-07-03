"""Persistable user-defined comparison view: criteria + weights (§24.13).

Пользовательский выбор критериев и весов с сохранением view. §24.13 требует
«поддержать пользовательский выбор критериев и весов с сохранением view»:
``mcda_scoring`` лишь считает баллы и не моделирует/не валидирует сохранённое
представление. Здесь описан неизменяемый ``ComparisonView`` — именованный набор
выбранных критериев и их нормализованных весов (в сумме 1.0), который можно
сериализовать (``as_dict``/``from_dict``) и восстановить без потерь.

A ``ComparisonView`` is an immutable, serializable record of a user's chosen
criteria and their weights. Weights are always stored NORMALIZED (rescaled to
sum to 1.0, preserving ratios); an all-zero weight vector degrades to an equal
split. ``build_view`` enforces that the weight keys are exactly the criteria
set, so a saved view can never reference an unknown or missing criterion.

- **normalize_weights** — пересчёт весов в сумму 1.0 с сохранением пропорций
  (все нули → равные доли) / rescale weights to sum 1.0 (all-zero → equal).
- **build_view** — валидирует ключи весов == множество критериев и сохраняет
  нормализованные веса / validate keys and store normalized weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Rescale ``weights`` to sum to 1.0, preserving ratios (§24.13).

    Пропорции сохраняются: ``{'a':1,'b':3}`` → ``{'a':0.25,'b':0.75}``. Если сумма
    равна нулю (все веса 0 или пусто-нет ключей), возвращается равномерное
    распределение по имеющимся ключам. All-zero (or all-equal-zero) weights map
    to an equal split so a view is never left with an undefined weighting.
    """
    keys = list(weights)
    total = sum(weights.values())
    if total <= 0.0:
        if not keys:
            return {}
        share = 1.0 / len(keys)
        return dict.fromkeys(keys, share)
    return {k: weights[k] / total for k in keys}


@dataclass(frozen=True)
class ComparisonView:
    """Сохранённое представление сравнения / a persisted comparison view.

    - ``view_id`` — идентификатор view / stable view identifier.
    - ``criteria`` — упорядоченный кортеж критериев / ordered criteria tuple.
    - ``weights`` — нормализованные веса (сумма 1.0) / normalized weights.
    - ``created_by`` — автор / creator identifier.
    - ``created_at`` — время создания (ISO-строка) / creation timestamp.
    """

    view_id: str
    criteria: tuple[str, ...]
    weights: dict[str, float]
    created_by: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        """Сериализуемое представление / serializable mapping of all fields."""
        return {
            "view_id": self.view_id,
            "criteria": list(self.criteria),
            "weights": dict(self.weights),
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComparisonView:
        """Восстановить view из ``as_dict`` без потерь / round-trip from mapping."""
        return cls(
            view_id=str(data["view_id"]),
            criteria=tuple(data["criteria"]),
            weights={str(k): float(v) for k, v in dict(data["weights"]).items()},
            created_by=str(data["created_by"]),
            created_at=str(data["created_at"]),
        )


def build_view(
    view_id: str,
    criteria: tuple[str, ...] | list[str],
    weights: dict[str, float],
    created_by: str,
    created_at: str,
) -> ComparisonView:
    """Build a validated ``ComparisonView`` with normalized weights (§24.13).

    Порядок критериев сохраняется, дубликаты удаляются (первое вхождение). Ключи
    ``weights`` должны точно совпадать с множеством критериев — иначе ``ValueError``
    (лишний вес не из критериев, либо у критерия отсутствует вес). Веса всегда
    сохраняются нормализованными (сумма 1.0). Criterion order is preserved and
    deduplicated; the weight keys must equal the criteria set exactly.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for name in criteria:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    criteria_set = set(ordered)
    weight_keys = set(weights)
    if weight_keys != criteria_set:
        extra = weight_keys - criteria_set
        missing = criteria_set - weight_keys
        raise ValueError(
            f"weights keys must equal criteria set: extra={sorted(extra)} missing={sorted(missing)}"
        )
    normalized = normalize_weights({k: weights[k] for k in ordered})
    return ComparisonView(
        view_id=view_id,
        criteria=tuple(ordered),
        weights=normalized,
        created_by=created_by,
        created_at=created_at,
    )
