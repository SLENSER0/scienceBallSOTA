"""Benchmark recall/abstention gate vs published SOTA numbers (§23.31/§23.35).

Гейт «дотягиваем ли до SOTA»: сравнивает НАШЕ измеренное число на бенчмарке с
ЛУЧШИМ опубликованным результатом из каталога §23.35 (см.
``docs/reference/sota_catalog_2025_2026.md``). Для бенчмарка берётся максимум по
всем опубликованным системам; ``meets_sota`` истинно, когда наш балл не ниже
этого максимума (ничья засчитывается как «дотянули»). Это НЕ
:mod:`sota_leaderboard_compare` (тот сравнивает произвольный набор метрик по
парам): здесь один бенчмарк → один порог = лучший опубликованный бейзлайн.

"Do we reach SOTA?" gate: compares OUR measured score on a benchmark against the
BEST published result in the §23.35 catalog. For a benchmark we take the max over
all published systems; ``meets_sota`` is true when our score is at least that max
(a tie counts as reaching SOTA).

Reference numbers (as reported by the §23.35 catalog — do not silently "fix"):

- **olmOCR-Bench** — olmOCR-2-7B-1025 **82.4** (vs Marker 76.1, MinerU2.5 75.2,
  GPT-4o 68.9). Source: olmOCR 2, arXiv:2510.19817, github.com/allenai/olmocr.
- **OmniDocBench** — MinerU2.5-Pro **95.75** / MinerU2.5 **93.04** (vs Qwen2-VL-72B
  89.78). Sources: MinerU 2.5, arXiv:2509.22186, github.com/opendatalab/MinerU;
  OmniDocBench, arXiv:2412.07626, github.com/opendatalab/OmniDocBench.
- **LightRAG** — win-rate vs NaiveRAG **60-85%**, ~parity with MS GraphRAG.
  Source: LightRAG, arXiv:2410.05779, github.com/HKUDS/LightRAG.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Rounding applied to ``gap`` before the sign is trusted — guards against float
# noise (e.g. ``93.04 - 93.04`` drifting off zero) near the boundary.
_GAP_NDIGITS = 9

# Best published SOTA numbers per benchmark, benchmark -> {system: score}, taken
# verbatim from the §23.35 catalog (``docs/reference/sota_catalog_2025_2026.md``).
# Numbers are "as reported"; higher is better for every benchmark here.
SOTA_BASELINES: dict[str, dict[str, float]] = {
    # olmOCR-Bench (OCR parsing) — olmOCR 2, arXiv:2510.19817.
    "olmOCR-Bench": {
        "olmOCR-2-7B-1025": 82.4,
        "Marker": 76.1,
        "MinerU2.5": 75.2,
        "GPT-4o": 68.9,
    },
    # OmniDocBench (end-to-end doc parsing) — MinerU 2.5, arXiv:2509.22186;
    # OmniDocBench, arXiv:2412.07626.
    "OmniDocBench": {
        "MinerU2.5-Pro": 95.75,
        "MinerU2.5": 93.04,
        "Qwen2-VL-72B": 89.78,
    },
}


@dataclass(frozen=True)
class SotaGate:
    """One benchmark checked against its best published baseline (§23.31/§23.35).

    ``our_score`` — наше измеренное число, ``best_baseline`` — лучший
    опубликованный результат по бенчмарку. ``gap = our_score - best_baseline``
    (плюс = обошли SOTA), ``meets_sota`` истинно при ``our_score >= best_baseline``.

    ``our_score`` is our measured number, ``best_baseline`` the best published
    result for the benchmark. ``gap = our_score - best_baseline`` (positive means
    we beat SOTA); ``meets_sota`` is ``our_score >= best_baseline``.
    """

    benchmark: str
    our_score: float
    best_baseline: float
    gap: float
    meets_sota: bool

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "benchmark": self.benchmark,
            "our_score": self.our_score,
            "best_baseline": self.best_baseline,
            "gap": self.gap,
            "meets_sota": self.meets_sota,
        }


def best_baseline(benchmark: str) -> float:
    """Best published score for ``benchmark`` (max over its systems).

    Неизвестный бенчмарк → :class:`KeyError` (громко, не молча).
    Unknown benchmark raises :class:`KeyError` (loud, not silent).
    """
    return max(SOTA_BASELINES[benchmark].values())


def gate(benchmark: str, our_score: float) -> SotaGate:
    """Gate ``our_score`` on ``benchmark`` against the best published baseline.

    Берётся максимум по опубликованным системам бенчмарка. ``gap`` округляется до
    ``_GAP_NDIGITS`` знаков перед проверкой знака, чтобы убрать шум float.
    ``meets_sota`` истинно при ``our_score >= best_baseline`` (ничья = дотянули).
    Неизвестный бенчмарк → :class:`KeyError`.

    Takes the max over the benchmark's published systems. ``gap`` is rounded to
    ``_GAP_NDIGITS`` digits before its sign is trusted, killing float noise;
    ``meets_sota`` is ``our_score >= best_baseline`` (a tie reaches SOTA). An
    unknown benchmark raises :class:`KeyError`.
    """
    best = best_baseline(benchmark)  # KeyError on unknown benchmark
    score = float(our_score)
    gap = round(score - best, _GAP_NDIGITS)
    meets_sota = gap >= 0.0
    return SotaGate(
        benchmark=benchmark,
        our_score=score,
        best_baseline=best,
        gap=gap,
        meets_sota=meets_sota,
    )
