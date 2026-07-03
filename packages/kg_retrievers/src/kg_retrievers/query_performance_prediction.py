"""§12.11 — post-retrieval query-performance predictors (QPP) over fused scores.

Given a *fused* score list (после слияния ранжирований / after rank fusion), we
predict retrieval quality / answerability for evaluation (§15) *without* touching
the query text — purely from the shape of the score distribution.

Отличие от ``answerability_estimate``: тот работает по наличию/отсутствию ячеек
покрытия (hit/gap), а здесь мы смотрим только на числовые оценки релевантности.

Predictors (по срезу top-k отсортированных по убыванию оценок):

* ``mean_top``  — среднее оценок в top-k (сила верхушки ранжирования);
* ``std_dev``   — популяционное СКО оценок top-k (разброс / spread);
* ``nqc``       — Normalized Query Commitment = ``std_dev / mean_top``
                  (``0.0`` при ``mean_top == 0``): нормированный разброс;
* ``wig``       — Weighted Information Gain = ``mean_top - corpus_mean``:
                  насколько верхушка выше среднего по корпусу;
* ``top_gap``   — ``score[0] - score[1]`` (``0.0`` при < 2 оценок): отрыв
                  лидера от второго кандидата.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

# -- defaults ---------------------------------------------------------------
DEFAULT_K = 10  # размер top-k среза / top-k slice size
DEFAULT_CORPUS_MEAN = 0.0  # опорное среднее по корпусу для WIG


@dataclass(frozen=True)
class QPPScores:
    """Набор QPP-предикторов по fused-оценкам / query-performance predictors.

    ``nqc`` — нормированный разброс (std_dev / mean_top); ``wig`` — прирост над
    средним по корпусу (mean_top - corpus_mean); ``std_dev`` — популяционное СКО
    top-k; ``top_gap`` — отрыв первого от второго; ``mean_top`` — среднее top-k.
    """

    nqc: float
    wig: float
    std_dev: float
    top_gap: float
    mean_top: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "nqc": self.nqc,
            "wig": self.wig,
            "std_dev": self.std_dev,
            "top_gap": self.top_gap,
            "mean_top": self.mean_top,
        }


def predict(
    scores: list[float],
    k: int = DEFAULT_K,
    corpus_mean: float = DEFAULT_CORPUS_MEAN,
) -> QPPScores:
    """Посчитать QPP-предикторы по списку fused-оценок / compute QPP predictors.

    Оценки сортируются по убыванию внутри функции (вход может быть любого
    порядка). Берётся top-k срез; ``k`` больше длины использует все оценки.
    Пустой вход -> все предикторы ``0.0``.
    """
    ordered = sorted(scores, reverse=True)
    if not ordered:
        return QPPScores(nqc=0.0, wig=0.0, std_dev=0.0, top_gap=0.0, mean_top=0.0)

    top = ordered[: max(k, 0)] or ordered  # top-k; k<=0 деградирует ко всем
    n = len(top)
    mean_top = sum(top) / n
    variance = sum((s - mean_top) ** 2 for s in top) / n  # population variance
    std_dev = sqrt(variance)
    nqc = std_dev / mean_top if mean_top != 0 else 0.0
    wig = mean_top - corpus_mean
    top_gap = ordered[0] - ordered[1] if len(ordered) >= 2 else 0.0

    return QPPScores(
        nqc=nqc,
        wig=wig,
        std_dev=std_dev,
        top_gap=top_gap,
        mean_top=mean_top,
    )
