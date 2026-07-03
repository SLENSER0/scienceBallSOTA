"""Pairwise system win-rate ranking for evaluation reports (§18.11).

When several candidate systems (retrievers, prompts, model variants) are scored
on the *same* aligned set of questions, a single mean metric hides *who beats
whom*. This module computes the classic **pairwise win-rate matrix**: for every
ordered pair ``(a, b)`` the fraction of questions on which ``a`` outscores
``b``. Systems are then ranked by their *mean pairwise win rate* — the average,
over all opponents, of that fraction — which is the standard head-to-head
tournament ranking used in leaderboard-style reporting.

Победа определяется по одному вопросу: у кого балл выше (или ниже, если
``higher_is_better=False``), тот и выиграл; равные баллы — ничья и в долю побед
не входят. ``matrix[a][b]`` — доля вопросов, где ``a`` побеждает ``b`` (ничьи
считаются как поражения для доли, но отражены в поле ``ties``). Ранжирование —
по средней доле побед, имя разрывает равенство.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SystemRank:
    """One system's aggregate standing across all pairwise comparisons.

    ``name`` — system identifier.
    ``mean_win_rate`` — mean of ``matrix[name][other]`` over all opponents.
    ``wins`` / ``losses`` / ``ties`` — total per-question outcomes summed over
    every opponent (a tie is neither a win nor a loss).
    """

    name: str
    mean_win_rate: float
    wins: int
    losses: int
    ties: int

    def as_dict(self) -> dict[str, str | float | int]:
        return {
            "name": self.name,
            "mean_win_rate": round(self.mean_win_rate, 4),
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
        }


@dataclass(frozen=True)
class WinRateReport:
    """Full pairwise win-rate report over an aligned scoring table.

    ``n_questions`` — number of aligned questions per system.
    ``matrix`` — ``matrix[a][b]`` is the fraction of questions where ``a`` beats
    ``b`` (ties excluded from the numerator); diagonal entries are omitted.
    ``ranking`` — systems ordered by descending ``mean_win_rate``, name ascending
    on ties.
    """

    n_questions: int
    matrix: dict[str, dict[str, float]]
    ranking: tuple[SystemRank, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "n_questions": self.n_questions,
            "matrix": {
                a: {b: round(frac, 4) for b, frac in row.items()} for a, row in self.matrix.items()
            },
            "ranking": [rank.as_dict() for rank in self.ranking],
        }


def _validate(scores: Mapping[str, Sequence[float]]) -> int:
    """Проверка входа: >= 2 систем и равные длины серий; возвращает ``n``."""
    if len(scores) < 2:
        raise ValueError("need at least two systems to compare")
    lengths = {len(series) for series in scores.values()}
    if len(lengths) != 1:
        raise ValueError("all systems must have the same number of scores")
    n = lengths.pop()
    if n < 1:
        raise ValueError("need at least one question to compare")
    return n


def win_rate_matrix(
    scores: Mapping[str, Sequence[float]],
    *,
    higher_is_better: bool = True,
) -> WinRateReport:
    """Compute the pairwise win-rate matrix and mean-win-rate ranking.

    ``scores`` maps each system name to its aligned per-question score series;
    all series must share the same length. On each question the system with the
    better score (higher by default, lower when ``higher_is_better=False``) wins;
    equal scores are ties and count toward neither side's win fraction.

    Fewer than two systems or unequal-length series raise ``ValueError``.
    """
    n = _validate(scores)
    names = sorted(scores)

    matrix: dict[str, dict[str, float]] = {a: {} for a in names}
    totals: dict[str, dict[str, int]] = {a: {"wins": 0, "losses": 0, "ties": 0} for a in names}
    for a in names:
        for b in names:
            if a == b:
                continue
            wins = 0
            for sa, sb in zip(scores[a], scores[b], strict=True):
                a_beats_b = sa > sb if higher_is_better else sa < sb
                if a_beats_b:
                    wins += 1
            matrix[a][b] = wins / n
            totals[a]["wins"] += wins

    # Losses/ties per system derive from the symmetric comparison already done.
    for a in names:
        for b in names:
            if a == b:
                continue
            a_wins = round(matrix[a][b] * n)
            b_wins = round(matrix[b][a] * n)
            totals[a]["losses"] += b_wins
            totals[a]["ties"] += n - a_wins - b_wins

    ranking: list[SystemRank] = []
    for a in names:
        opponents = matrix[a]
        mean = sum(opponents.values()) / len(opponents)
        ranking.append(
            SystemRank(
                name=a,
                mean_win_rate=mean,
                wins=totals[a]["wins"],
                losses=totals[a]["losses"],
                ties=totals[a]["ties"],
            )
        )
    ranking.sort(key=lambda r: (-r.mean_win_rate, r.name))

    return WinRateReport(
        n_questions=n,
        matrix=matrix,
        ranking=tuple(ranking),
    )
