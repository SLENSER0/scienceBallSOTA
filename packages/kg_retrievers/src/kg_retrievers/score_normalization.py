"""Per-source score normalization before fusion (§12.3 Mode B).

Публичный нормализатор score по источнику (min-max или z-score) перед fusion.
Public per-source score normalization applied independently for each source
prior to rank/score fusion. Complements the private ``scoring._minmax`` helper
by exposing a reusable min-max normalizer plus a z-score alternative and a
multi-source dispatcher.

- **minmax_normalize** — линейно масштабирует значения в [0,1] (min→0, max→1).
- **zscore_normalize** — стандартизует значения (вычесть среднее, делить на
  популяционное СКО); нулевая дисперсия → все 0.0.
- **normalize_per_source** — применяет выбранный метод к каждому источнику
  независимо (a source's own min/max/mean define its own scale).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Supported normalization methods (§12.3).
_METHODS = ("minmax", "zscore")


@dataclass(frozen=True)
class NormalizationResult:
    """Результат нормализации / normalized scores tagged with the method used."""

    method: str
    scores: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        """Сериализуемое представление / serializable ``{method, scores}``."""
        return {"method": self.method, "scores": dict(self.scores)}


def minmax_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Min-max scale to [0,1]: min→0.0, max→1.0; all-equal input → all 0.0.

    Constant input maps to 0.0 (a neutral baseline) rather than dividing by
    zero. Negative raw values are handled naturally (the minimum maps to 0.0).
    """
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    span = hi - lo
    if span <= 0.0:
        return dict.fromkeys(scores, 0.0)
    return {k: (float(v) - lo) / span for k, v in scores.items()}


def zscore_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Standardize by mean and population std; zero-variance → all 0.0.

    Uses the population standard deviation (divide by ``n``). When every value
    is identical the variance is zero and all outputs are 0.0.
    """
    if not scores:
        return {}
    values = [float(v) for v in scores.values()]
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    if variance <= 0.0:
        return dict.fromkeys(scores, 0.0)
    std = variance**0.5
    return {k: (float(v) - mean) / std for k, v in scores.items()}


def _normalizer(method: str) -> Any:
    if method == "minmax":
        return minmax_normalize
    if method == "zscore":
        return zscore_normalize
    raise ValueError(f"unknown normalization method: {method!r} (expected one of {_METHODS})")


def normalize_per_source(
    by_source: dict[str, dict[str, float]], method: str = "minmax"
) -> dict[str, dict[str, float]]:
    """Normalize each source's scores independently with ``method`` (§12.3).

    ``by_source`` maps a source name (dense/keyword/graph/…) to
    ``{candidate_id: raw_score}``. Each source is normalized on its own scale,
    so a source's own extreme maps to 1.0 (min-max) regardless of the others.
    Raises ``ValueError`` for an unknown ``method``.
    """
    fn = _normalizer(method)
    return {source: fn(scores) for source, scores in by_source.items()}
