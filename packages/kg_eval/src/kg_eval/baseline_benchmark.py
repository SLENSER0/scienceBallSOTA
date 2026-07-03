"""Baseline/ablation benchmark: N-system per-metric winner table (§23.31).

Сравнение нескольких систем (базовые линии A–D против «полной» системы) по
набору метрик, где у каждой метрики своё направление «лучше»: для одних больше —
лучше (recall, mrr), для других меньше — лучше (latency, cost). Для каждой
метрики выбирается победитель с учётом направления, а «дельта полной системы»
считается как разница со лучшим конкурентом и нормализуется по знаку так, что
положительное значение всегда означает выигрыш полной системы. Вердикт —
``"sota"``, если полная система выигрывает большинство метрик, иначе
``"not_sota"``. Это НЕ :mod:`eval_diff` (два прогона, «больше — лучше»): здесь
N систем и у каждой метрики собственное направление.

Baseline/ablation benchmark comparing N systems (baselines A–D vs the full
system) across metrics, each with its own direction. Per metric a winner is
picked respecting that direction; ``full_delta`` is the full system's score minus
the best competing baseline, sign-adjusted so a positive value always means the
full system won. ``verdict`` is ``"sota"`` iff the full system wins a majority of
metrics, else ``"not_sota"``. Distinct from :mod:`eval_diff` (two runs, all
higher-is-better): here there are N systems and per-metric directions.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Rounding applied to ``full_delta`` before its sign test — guards against float
# noise (e.g. ``0.62 - 0.6 == 0.020000000000000018``) near the zero boundary.
_DELTA_NDIGITS = 9

_SOTA = "sota"
_NOT_SOTA = "not_sota"


@dataclass(frozen=True)
class MetricRow:
    """One metric compared across all systems — направление, счёты, победитель (§23.31).

    ``higher_is_better`` fixes the metric's direction. ``scores`` are ``(system,
    score)`` pairs sorted by system name. ``winner`` is the best system for this
    metric (ties → lexicographically-smallest name). ``full_delta`` is the full
    system's score minus the best competing baseline, sign-adjusted so positive
    means the full system beat the best baseline.
    """

    metric: str
    higher_is_better: bool
    scores: tuple[tuple[str, float], ...]
    winner: str
    full_delta: float

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); ``scores`` becomes a list of pairs."""
        return {
            "metric": self.metric,
            "higher_is_better": self.higher_is_better,
            "scores": [[s, v] for s, v in self.scores],
            "winner": self.winner,
            "full_delta": self.full_delta,
        }


@dataclass(frozen=True)
class BenchmarkComparison:
    """N-system benchmark verdict — победители по метрикам и итог (§23.31).

    ``metrics`` are sorted by metric name for determinism. ``full_wins`` /
    ``full_losses`` count metrics where the full system strictly beat / lost to
    the best baseline (equal scores are ties, counted in neither). Invariant:
    ``full_wins + full_losses + ties == len(metrics)``. ``verdict`` is
    ``"sota"`` iff ``full_wins > full_losses``.
    """

    metrics: tuple[MetricRow, ...]
    full_system: str
    full_wins: int
    full_losses: int
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); ``metrics`` becomes a list of dicts."""
        return {
            "metrics": [m.as_dict() for m in self.metrics],
            "full_system": self.full_system,
            "full_wins": self.full_wins,
            "full_losses": self.full_losses,
            "verdict": self.verdict,
        }


def compare(
    systems: Mapping[str, Mapping[str, float]],
    *,
    full_system: str,
    directions: Mapping[str, bool],
) -> BenchmarkComparison:
    """Compare ``systems`` per metric → :class:`BenchmarkComparison` (§23.31).

    Для каждой метрики из ``directions`` собираются счёты всех систем (отсутствие
    метрики у системы — ``KeyError``). Победитель — ``max`` при
    ``higher_is_better`` иначе ``min``; ничьи разрешаются в пользу лексикографически
    наименьшего имени. ``full_delta`` = счёт полной системы минус лучший счёт
    конкурента, нормализованный по знаку (плюс = выигрыш полной системы). Метрика
    засчитывается полной системе при ``full_delta > 0``, проигрывается при
    ``< 0``, ничья при ``== 0``. Вердикт — ``"sota"`` при большинстве побед.

    Every system must define every metric in ``directions`` — a missing metric
    raises :class:`KeyError`. The winner is the ``max``/``min`` score per the
    metric's direction, ties broken to the lexicographically-smallest name.
    ``full_delta`` is sign-adjusted so positive always means the full system beat
    the best competing baseline; the metric is a full win / loss / tie for
    ``full_delta`` ``> 0`` / ``< 0`` / ``== 0``.
    """
    # Fail loudly if the full system itself is unknown.
    _ = systems[full_system]
    rows: list[MetricRow] = []
    full_wins = 0
    full_losses = 0
    for metric in sorted(directions):
        higher_is_better = bool(directions[metric])
        # Missing metric for any system raises KeyError here.
        pairs = [(name, float(systems[name][metric])) for name in sorted(systems)]
        scores = tuple(pairs)
        winner = _pick_winner(pairs, higher_is_better=higher_is_better)
        full_delta = _full_delta(pairs, full_system=full_system, higher_is_better=higher_is_better)
        rows.append(
            MetricRow(
                metric=metric,
                higher_is_better=higher_is_better,
                scores=scores,
                winner=winner,
                full_delta=full_delta,
            )
        )
        if full_delta > 0.0:
            full_wins += 1
        elif full_delta < 0.0:
            full_losses += 1
    verdict = _SOTA if full_wins > full_losses else _NOT_SOTA
    return BenchmarkComparison(
        metrics=tuple(rows),
        full_system=full_system,
        full_wins=full_wins,
        full_losses=full_losses,
        verdict=verdict,
    )


def _pick_winner(pairs: list[tuple[str, float]], *, higher_is_better: bool) -> str:
    """Best system for a metric — победитель с учётом направления и ничьих.

    ``max`` score if ``higher_is_better`` else ``min``; ties resolved to the
    lexicographically-smallest system name.
    """
    best = max(v for _, v in pairs) if higher_is_better else min(v for _, v in pairs)
    return min(name for name, v in pairs if v == best)


def _full_delta(
    pairs: list[tuple[str, float]], *, full_system: str, higher_is_better: bool
) -> float:
    """Full system's sign-adjusted margin over the best competing baseline.

    Positive means the full system beats the best baseline. With no competitors
    the margin is ``0.0`` (a tie).
    """
    full_score = next(v for name, v in pairs if name == full_system)
    comp = [v for name, v in pairs if name != full_system]
    if not comp:
        return 0.0
    delta = full_score - max(comp) if higher_is_better else min(comp) - full_score
    return round(delta, _DELTA_NDIGITS)
