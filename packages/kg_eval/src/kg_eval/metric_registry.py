"""Eval-metric registry — canonical metric definitions + direction helpers (§18.10).

Pure-python, dependency-free catalog of the evaluation metrics the harness reports
(§15.2/§18.6/§18.7). Each metric is described once by a frozen :class:`MetricDef`
carrying its ``name``, ``higher_is_better`` direction, valid ``range`` and a short
bilingual ``description``. Downstream code (quality gates, reports, leaderboards)
looks a metric up by name via :func:`metric_for` and compares two scores in the
metric's own direction via :func:`is_better` — так gate-логика не хардкодит,
у какой метрики "больше == лучше".

The registry is the single source of truth: adding a metric here makes it known
everywhere without touching comparison call-sites.
"""

from __future__ import annotations

from dataclasses import dataclass

# Every registered metric is a normalized score in the closed unit interval.
UNIT_RANGE: tuple[float, float] = (0.0, 1.0)


@dataclass(frozen=True)
class MetricDef:
    """Immutable description of a single eval metric (§18.10).

    ``range`` is the inclusive ``(low, high)`` interval a valid value may take.
    ``higher_is_better`` fixes the optimisation direction so comparisons need not
    special-case each metric (см. :func:`is_better`).
    """

    name: str
    higher_is_better: bool
    range: tuple[float, float]
    description: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — ``range`` as a two-element list (§21 report I/O)."""
        return {
            "name": self.name,
            "higher_is_better": self.higher_is_better,
            "range": [self.range[0], self.range[1]],
            "description": self.description,
        }


# --- Canonical registry ------------------------------------------------------
# Order is the reporting order; keyed by name below. All current metrics are
# unit-range and higher-is-better (§15.2 targets: recall/MRR/nDCG вверх).
_DEFS: tuple[MetricDef, ...] = (
    MetricDef(
        name="recall_at_k",
        higher_is_better=True,
        range=UNIT_RANGE,
        description="Recall@k: доля релевантных evidence-чанков в топ-k (§15.2).",
    ),
    MetricDef(
        name="mrr",
        higher_is_better=True,
        range=UNIT_RANGE,
        description="Mean reciprocal rank первого релевантного результата (§15.2).",
    ),
    MetricDef(
        name="ndcg",
        higher_is_better=True,
        range=UNIT_RANGE,
        description="Normalized DCG — ранжирующее качество с учётом позиций (§18.6).",
    ),
    MetricDef(
        name="extraction_f1",
        higher_is_better=True,
        range=UNIT_RANGE,
        description="F1 извлечённых сущностей/связей против golden-набора (§18.6).",
    ),
    MetricDef(
        name="answer_grounding",
        higher_is_better=True,
        range=UNIT_RANGE,
        description="Grounding: доля ответа, подтверждённая цитируемыми evidence (§18.7).",
    ),
)

METRICS: dict[str, MetricDef] = {d.name: d for d in _DEFS}
"""Registry mapping metric ``name`` -> :class:`MetricDef` (single source of truth)."""


def metric_for(name: str) -> MetricDef | None:
    """Look up a metric by name; ``None`` for an unknown metric (§18.10)."""
    return METRICS.get(name)


def is_better(name: str, a: float, b: float) -> bool:
    """``True`` iff score ``a`` is strictly better than ``b`` for metric ``name``.

    Direction follows the metric's ``higher_is_better`` flag; equal values are not
    "better" (returns ``False``). Raises ``KeyError`` for an unknown metric so
    gate-логика не сравнивает по неизвестному направлению молча.
    """
    metric = metric_for(name)
    if metric is None:
        raise KeyError(f"unknown metric: {name!r}")
    return a > b if metric.higher_is_better else a < b
