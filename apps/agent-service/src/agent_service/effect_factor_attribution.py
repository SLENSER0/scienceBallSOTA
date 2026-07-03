"""§13.17 «что влияет на эффект» — per-factor effect attribution.

Where :mod:`answer_tabs` only computes a *flat* :func:`effect_range` for the
summary tab, this module answers the sharper question of the §13.17 answer
synthesizer: *what processing factor drives the divergence in effect?* Оно
группирует ряды экспериментов по одному фактору обработки и считает разброс
эффекта в каждой корзине.

Given experiment rows shaped like::

    {"processing": {"temperature_c": 180, "time_h": 4, "composition": "A"},
     "effect": 12.5}

:func:`attribute_effects` buckets those rows by ``row['processing'][factor]``,
computes count and effect min/max/mean per bucket, drops rows missing the
factor or a numeric effect (``bool`` is rejected — ``bool`` is not a
measurement), and returns :class:`FactorBucket` values sorted widest-spread
first (``effect_max - effect_min``), ties broken by descending ``effect_mean``.

Pure-python and deterministic: nothing here touches the graph store or the LLM,
so the module is unit-testable without a seeded Kuzu base. Kuzu note: custom
node props are NOT queryable columns — a retriever must RETURN base columns and
read the rest via ``get_node``; by the time rows reach this module they already
carry the merged ``processing`` props as plain dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["FactorBucket", "attribute_effects"]


@dataclass(frozen=True)
class FactorBucket:
    """Один уровень фактора обработки и разброс эффекта по нему (§13.17).

    Aggregates every experiment row sharing one ``value`` of the grouping
    ``factor``: how many rows (``n``) and the min/max/mean of their numeric
    ``effect``. A single-row bucket has ``effect_min == effect_max ==
    effect_mean``.
    """

    factor: str
    value: Any
    n: int
    effect_min: float
    effect_max: float
    effect_mean: float

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain, orjson-ready ``dict`` (§13.17 payload row)."""
        return {
            "factor": self.factor,
            "value": self.value,
            "n": self.n,
            "effect_min": self.effect_min,
            "effect_max": self.effect_max,
            "effect_mean": self.effect_mean,
        }


def _numeric_effect(row: dict[str, Any]) -> float | None:
    """Return the row's numeric ``effect`` as ``float``, or ``None`` if unusable.

    Booleans are rejected (``bool`` is a subtype of ``int`` but not a
    measurement); anything non-``int``/``float`` yields ``None``.
    """
    effect = row.get("effect")
    if isinstance(effect, bool) or not isinstance(effect, (int, float)):
        return None
    return float(effect)


def attribute_effects(rows: list[dict], factor: str) -> list[FactorBucket]:
    """Bucket ``rows`` by ``processing[factor]`` and rank by effect spread (§13.17).

    Группировка рядов по значению фактора: для каждого уникального
    ``row['processing'][factor]`` собираем численные эффекты и считаем
    count / min / max / mean. Пропускаем ряды без фактора или без численного
    (не-``bool``) эффекта. Результат отсортирован по убыванию разброса
    (``effect_max - effect_min``), ничьи — по убыванию ``effect_mean``.
    """
    grouped: dict[Any, list[float]] = {}
    order: list[Any] = []
    for row in rows:
        processing = row.get("processing")
        if not isinstance(processing, dict) or factor not in processing:
            continue
        effect = _numeric_effect(row)
        if effect is None:
            continue
        value = processing[factor]
        if value not in grouped:
            grouped[value] = []
            order.append(value)
        grouped[value].append(effect)

    buckets = [
        FactorBucket(
            factor=factor,
            value=value,
            n=len(effects),
            effect_min=min(effects),
            effect_max=max(effects),
            effect_mean=sum(effects) / len(effects),
        )
        for value in order
        for effects in (grouped[value],)
    ]
    buckets.sort(
        key=lambda b: (b.effect_max - b.effect_min, b.effect_mean),
        reverse=True,
    )
    return buckets
