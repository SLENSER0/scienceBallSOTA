"""Bland-Altman numeric agreement report (§18.10).

``numeric_check`` отвечает на бинарный вопрос «попал ли ответ в допуск», но не
показывает *систематическое* смещение: если модель стабильно завышает числа на
единицу, поштучная проверка это скрывает. / ``numeric_check`` answers the binary
«did the answer fall within tolerance», but it hides *systematic* bias — a model
that consistently overshoots by one unit still fails silently per-item.

Bland-Altman анализ дополняет точечную/допусковую проверку: считаем среднюю
разность (смещение/bias), выборочное СКО разностей, 95%-границы согласия
(bias ± 1.96·sd), среднюю абсолютную ошибку и долю ответов в допуске. / The
Bland-Altman analysis complements the exact/tolerance ``numeric_check`` by
quantifying the mean difference (bias), the sample sd of differences, the 95%
limits of agreement (bias ± 1.96·sd), the mean absolute error, and the fraction
of answers within tolerance. Pure stdlib, fully reproducible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# 95%-квантиль стандартного нормального распределения. / 95% normal z-quantile.
_Z_95 = 1.96


@dataclass(frozen=True)
class AgreementReport:
    """Отчёт согласия Bland-Altman. / Bland-Altman agreement report.

    ``bias`` — среднее (pred - gold); ``sd_diff`` — выборочное СКО разностей.
    ``loa_lower``/``loa_upper`` — 95%-границы согласия bias ± 1.96·sd_diff.
    ``mae`` — средняя абсолютная ошибка; ``within_tol_fraction`` — доля
    |pred - gold| <= tolerance. / ``bias`` is mean (pred - gold); ``sd_diff``
    the sample sd of differences; ``loa_lower``/``loa_upper`` the 95% limits of
    agreement; ``mae`` the mean absolute error; ``within_tol_fraction`` the
    fraction of items with ``|pred - gold| <= tolerance``.
    """

    n: int
    bias: float
    sd_diff: float
    loa_lower: float
    loa_upper: float
    mae: float
    within_tol_fraction: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "bias": self.bias,
            "sd_diff": self.sd_diff,
            "loa_lower": self.loa_lower,
            "loa_upper": self.loa_upper,
            "mae": self.mae,
            "within_tol_fraction": self.within_tol_fraction,
        }


def bland_altman(
    pred: Sequence[float],
    gold: Sequence[float],
    *,
    tolerance: float = 0.0,
) -> AgreementReport:
    """Построить отчёт согласия Bland-Altman. / Build a Bland-Altman report.

    Пустые входы или разная длина -> ValueError. / Empty inputs or a length
    mismatch raise ``ValueError``.

    Разности ``d_i = pred_i - gold_i``; ``bias`` — их среднее, ``sd_diff`` —
    выборочное СКО (ddof=1, ноль при n < 2). Границы согласия — bias ± 1.96·sd.
    / Differences ``d_i = pred_i - gold_i``; ``bias`` is their mean, ``sd_diff``
    the sample sd (ddof=1, zero when n < 2). Limits are bias ± 1.96·sd.
    """
    if len(pred) != len(gold):
        raise ValueError("pred and gold must have equal length")
    n = len(pred)
    if n == 0:
        raise ValueError("pred and gold must be non-empty")

    diffs = [p - g for p, g in zip(pred, gold, strict=True)]
    bias = sum(diffs) / n

    if n < 2:
        sd_diff = 0.0
    else:
        var = sum((d - bias) ** 2 for d in diffs) / (n - 1)
        sd_diff = var**0.5

    loa_lower = bias - _Z_95 * sd_diff
    loa_upper = bias + _Z_95 * sd_diff

    abs_errors = [abs(d) for d in diffs]
    mae = sum(abs_errors) / n
    within = sum(1 for e in abs_errors if e <= tolerance)
    within_tol_fraction = within / n

    return AgreementReport(
        n=n,
        bias=bias,
        sd_diff=sd_diff,
        loa_lower=loa_lower,
        loa_upper=loa_upper,
        mae=mae,
        within_tol_fraction=within_tol_fraction,
    )
