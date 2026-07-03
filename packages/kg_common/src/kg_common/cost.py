"""LLM cost accounting — учёт стоимости вызовов LLM (§18.10).

Pure-python cost math over token counts. A :class:`ModelPrice` names the per-1k
input/output USD rates for one model; :func:`cost_for` multiplies token counts by
those rates into a frozen :class:`UsageCost`. :func:`aggregate_costs` folds many
usages into totals plus a per-model breakdown, and :func:`cost_per_unit` divides a
total by a unit count (documents/queries) with a guard against division by zero.

Everything here is deterministic and side-effect free:

* :class:`ModelPrice` — frozen per-model USD rates («тариф модели»).
* :class:`UsageCost`  — frozen per-call cost record with :meth:`UsageCost.as_dict`.
* :data:`PRICES`      — default price table keyed by ``model_id``.
* :func:`cost_for`    — token counts → :class:`UsageCost` (``KeyError`` on unknown).
* :func:`aggregate_costs` — totals + ``by_model`` breakdown over a list.
* :func:`cost_per_unit`   — ``total_usd / n_units``, ``0.0`` on empty denominator.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PRICES",
    "ModelPrice",
    "UsageCost",
    "aggregate_costs",
    "cost_for",
    "cost_per_unit",
]

# Rounding precision for serialized USD amounts — точность округления (6 знаков).
_USD_DP = 6


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Immutable per-model USD rates — тариф модели за 1k токенов (§18.10).

    ``input_usd_per_1k``/``output_usd_per_1k`` are the price in USD for one
    thousand prompt/completion tokens respectively. The record is a plain frozen
    value so it can be hashed, compared and used as a dict value.
    """

    model_id: str
    input_usd_per_1k: float
    output_usd_per_1k: float


@dataclass(frozen=True, slots=True)
class UsageCost:
    """Immutable per-call cost — стоимость одного вызова LLM (§18.10).

    ``prompt_tokens``/``completion_tokens`` are the token counts billed and
    ``cost_usd`` is their computed USD cost. :meth:`as_dict` serializes the record
    with ``cost_usd`` rounded to six decimal places for stable reporting.
    """

    model_id: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

    def as_dict(self) -> dict[str, object]:
        """Serialize with ``cost_usd`` rounded to 6 dp — словарь для отчёта.

        Keys are emitted in a fixed, sorted-stable order so downstream diffs and
        snapshots stay deterministic («порядок ключей стабилен»).
        """
        return {
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, _USD_DP),
            "model_id": self.model_id,
            "prompt_tokens": self.prompt_tokens,
        }


# Default price table — базовая таблица тарифов (placeholder OSS-local rates).
# Real deployments override this by passing an explicit ``prices`` mapping.
PRICES: dict[str, ModelPrice] = {
    "local-small": ModelPrice("local-small", 0.0, 0.0),
    "local-large": ModelPrice("local-large", 0.0, 0.0),
}


def cost_for(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    prices: dict[str, ModelPrice] = PRICES,
) -> UsageCost:
    """Compute the USD cost of one call — стоимость одного вызова (§18.10).

    Looks up ``model_id`` in ``prices`` (raising :class:`KeyError` for an unknown
    model), then bills ``prompt_tokens`` at the input rate and
    ``completion_tokens`` at the output rate. Cost scales as ``tokens / 1000``
    times the per-1k rate, itself carried in thousandths of a USD, so 1000 prompt
    tokens at a rate of ``2.0`` cost ``0.002`` USD («тариф в тысячных доллара»).
    """
    price = prices[model_id]
    cost = (
        prompt_tokens / 1000.0 * price.input_usd_per_1k / 1000.0
        + completion_tokens / 1000.0 * price.output_usd_per_1k / 1000.0
    )
    return UsageCost(
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
    )


def aggregate_costs(usages: list[UsageCost]) -> dict[str, object]:
    """Fold usages into totals + per-model breakdown — свод затрат (§18.10).

    Returns ``total_usd``, ``total_prompt_tokens``, ``total_completion_tokens``
    and ``by_model`` — a mapping ``model_id -> {cost_usd, prompt_tokens,
    completion_tokens}`` summed across all usages for that model. An empty list
    yields all-zero totals and an empty ``by_model``.
    """
    total_usd = 0.0
    total_prompt = 0
    total_completion = 0
    by_model: dict[str, dict[str, float]] = {}
    for usage in usages:
        total_usd += usage.cost_usd
        total_prompt += usage.prompt_tokens
        total_completion += usage.completion_tokens
        bucket = by_model.setdefault(
            usage.model_id,
            {"cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0},
        )
        bucket["cost_usd"] += usage.cost_usd
        bucket["prompt_tokens"] += usage.prompt_tokens
        bucket["completion_tokens"] += usage.completion_tokens
    for bucket in by_model.values():
        bucket["cost_usd"] = round(bucket["cost_usd"], _USD_DP)
    return {
        "total_usd": round(total_usd, _USD_DP),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "by_model": by_model,
    }


def cost_per_unit(usages: list[UsageCost], n_units: int) -> float:
    """Average USD cost per unit — стоимость на единицу (§18.10).

    Divides the aggregated ``total_usd`` by ``n_units`` (documents extracted or
    queries answered). Returns ``0.0`` when ``n_units`` is ``0`` to guard against
    division by zero («защита от деления на ноль»).
    """
    if n_units == 0:
        return 0.0
    total_usd = sum(usage.cost_usd for usage in usages)
    return round(total_usd / n_units, _USD_DP)
