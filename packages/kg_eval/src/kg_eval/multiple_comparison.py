"""Multiple-comparison correction for multi-metric benchmarks (§23.31).

``paired_bootstrap.py`` yields one ``p_value`` per metric, but claiming a
system is «significantly better» across *many* metrics at once inflates the
family-wise false-positive rate — with ``m`` independent tests at ``alpha`` the
chance of at least one spurious win is ``1 - (1 - alpha)**m``. This module
corrects a whole family of per-metric p-values so that reproducible benchmarks
report honest significance (§23.31: коррекция множественных сравнений, чтобы
«значимо лучше» по многим метрикам не раздувало ложноположительные срабатывания).

Two complementary procedures over the same :class:`CorrectionReport` shape:

* :func:`holm_bonferroni` — step-down family-wise control (strong FWER), the
  conservative choice; строгий контроль вероятности хоть одного ложного
  открытия.
* :func:`benjamini_hochberg` — step-up false-discovery-rate control, at least
  as lenient as Holm on the same input; контроль доли ложных открытий (FDR).

Both are pure-stdlib and deterministic: sorting by ``p`` value with a stable
tie-break on the metric name gives identical output for identical input.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectedResult:
    """One metric's outcome after multiple-comparison correction (§23.31).

    ``name`` — имя метрики; ``p_value`` — исходный (raw) p-value; ``adjusted_p``
    — скорректированное значение, клампится в ``[0.0, 1.0]``; ``significant`` —
    ``adjusted_p <= alpha`` под выбранной процедурой.
    """

    name: str
    p_value: float
    adjusted_p: float
    significant: bool

    def as_dict(self) -> dict[str, float | str | bool]:
        return {
            "name": self.name,
            "p_value": round(self.p_value, 6),
            "adjusted_p": round(self.adjusted_p, 6),
            "significant": self.significant,
        }


@dataclass(frozen=True)
class CorrectionReport:
    """Family-wide correction summary over a set of metric p-values (§23.31).

    ``method`` — ``"holm-bonferroni"`` или ``"benjamini-hochberg"``; ``alpha`` —
    порог значимости; ``n`` — число метрик в семье; ``n_significant`` — сколько
    из них остались значимыми после коррекции; ``results`` — по одной
    :class:`CorrectedResult` на каждый входной ключ, в порядке подачи.
    """

    method: str
    alpha: float
    n: int
    n_significant: int
    results: tuple[CorrectedResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "alpha": self.alpha,
            "n": self.n,
            "n_significant": self.n_significant,
            "results": [r.as_dict() for r in self.results],
        }


def _clamp_unit(value: float) -> float:
    """Clamp ``value`` into the closed unit interval ``[0.0, 1.0]``."""
    return min(1.0, max(0.0, value))


def _ordered_names(pvals: Mapping[str, float]) -> list[str]:
    """Metric names sorted by ``(p_value, name)`` for a deterministic order."""
    return sorted(pvals, key=lambda name: (float(pvals[name]), name))


def _build_report(
    method: str,
    pvals: Mapping[str, float],
    alpha: float,
    adjusted_by_name: Mapping[str, float],
) -> CorrectionReport:
    """Assemble a :class:`CorrectionReport`, one result per input key in order.

    ``adjusted_by_name`` supplies the already-clamped adjusted p-value for every
    metric. Significance is ``adjusted_p <= alpha``. ``results`` preserves the
    input mapping's key order (not the internal sort order).
    """
    results = tuple(
        CorrectedResult(
            name=name,
            p_value=float(raw),
            adjusted_p=adjusted_by_name[name],
            significant=adjusted_by_name[name] <= alpha,
        )
        for name, raw in pvals.items()
    )
    n_significant = sum(1 for r in results if r.significant)
    return CorrectionReport(
        method=method,
        alpha=alpha,
        n=len(results),
        n_significant=n_significant,
        results=results,
    )


def holm_bonferroni(pvals: Mapping[str, float], alpha: float = 0.05) -> CorrectionReport:
    """Holm-Bonferroni step-down family-wise correction (§23.31).

    Sorts the ``n`` p-values ascending and adjusts the ``i``-th (0-based) by the
    remaining-test multiplier ``(n - i)``: ``adjusted = (n - i) * p``. A running
    ``max`` enforces monotonicity so that once a test in the ordered sequence
    fails, every larger p-value inherits that failure (step-down). Each adjusted
    value is clamped to ``[0.0, 1.0]``; a metric is significant when its adjusted
    p-value ``<= alpha``. Empty input yields an empty report.
    """
    order = _ordered_names(pvals)
    n = len(order)
    adjusted_by_name: dict[str, float] = {}
    running = 0.0
    for i, name in enumerate(order):
        raw = float(pvals[name])
        candidate = _clamp_unit((n - i) * raw)
        running = max(running, candidate)
        adjusted_by_name[name] = running
    return _build_report("holm-bonferroni", pvals, alpha, adjusted_by_name)


def benjamini_hochberg(pvals: Mapping[str, float], alpha: float = 0.05) -> CorrectionReport:
    """Benjamini-Hochberg step-up false-discovery-rate correction (§23.31).

    Sorts the ``n`` p-values ascending and adjusts the rank-``k`` value
    (``k = 1..n``) by ``adjusted = p * n / k``. A running ``min`` swept from the
    largest p-value downwards enforces monotonicity (step-up). Each adjusted
    value is clamped to ``[0.0, 1.0]``; a metric is significant when its adjusted
    p-value ``<= alpha``. BH is at least as lenient as Holm on the same input, so
    ``n_significant`` here is ``>=`` the Holm count. Empty input yields an empty
    report.
    """
    order = _ordered_names(pvals)
    n = len(order)
    adjusted_by_name: dict[str, float] = {}
    running = 1.0
    # Sweep from the largest p-value (rank n) down to rank 1.
    for rank in range(n, 0, -1):
        name = order[rank - 1]
        raw = float(pvals[name])
        candidate = _clamp_unit(raw * n / rank)
        running = min(running, candidate)
        adjusted_by_name[name] = running
    return _build_report("benjamini-hochberg", pvals, alpha, adjusted_by_name)
