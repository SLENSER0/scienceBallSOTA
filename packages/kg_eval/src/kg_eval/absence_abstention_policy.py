"""Selective absence-claim abstention policy — cutoff selector (§25.15).

An absence claim ("no such relation exists in the graph") should only be *asserted*
when the model is confident enough that the claim is right. Ranking claims by
confidence (descending) and asserting only the highest-confidence prefix trades
**coverage** (какая доля absence-claims обслужена) against the **false-gap rate**
(доля неверных absence-claims среди принятых — ложно объявленных "пробелов").

This module is a *constraint-satisfaction cutoff selector*: given a budget on the
false-gap rate it picks the single confidence cutoff that **maximizes coverage**
subject to that budget. It is deliberately distinct from ``selective_risk_coverage``,
which plots the *full* risk-coverage curve and integrates AURC across every
threshold — here we return one operating point, not a curve.

Each record is ``(confidence: float, correct: bool)``: the self-reported confidence
in an absence claim and whether that claim was actually right. Records are sorted by
confidence descending (stable — ties keep input order, so детерминирован). We accept
the *longest* high-confidence prefix whose error rate ``errors/len`` stays ``<=``
``max_false_gap_rate``; the ``cutoff`` is the confidence of the last accepted record
(``1.0`` if nothing is accepted). Coverage is ``n_accepted / n`` (``0.0`` on empty
input, no division error). Raising the budget never lowers coverage (monotonic),
because a larger budget can only admit longer prefixes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class AbstentionPolicy:
    """One chosen operating point for absence-claim abstention (§25.15).

    ``cutoff`` is the confidence of the last accepted claim (``1.0`` if none were
    accepted); assert an absence claim iff its confidence ``>= cutoff``. ``coverage``
    is the accepted fraction ``n_accepted / n`` (``0.0`` on empty input);
    ``false_gap_rate`` is ``errors / n_accepted`` among the accepted prefix (``0.0``
    when nothing is accepted); ``n_accepted`` is the prefix length.
    """

    cutoff: float
    coverage: float
    false_gap_rate: float
    n_accepted: int

    def as_dict(self) -> dict[str, object]:
        return {
            "cutoff": self.cutoff,
            "coverage": self.coverage,
            "false_gap_rate": self.false_gap_rate,
            "n_accepted": self.n_accepted,
        }


def select_cutoff(
    records: Sequence[tuple[float, bool]], max_false_gap_rate: float
) -> AbstentionPolicy:
    """Pick the confidence cutoff maximizing coverage under a false-gap budget (§25.15).

    Sorts ``records`` by confidence descending (stable) and accepts the longest
    prefix whose error rate ``errors/len <= max_false_gap_rate``. Returns the
    resulting :class:`AbstentionPolicy`. Empty input yields ``n_accepted == 0``,
    ``coverage == 0.0`` and ``cutoff == 1.0`` без деления на ноль; a budget that
    admits no prefix likewise returns ``cutoff == 1.0`` and ``n_accepted == 0``.
    """
    ordered = sorted(records, key=lambda r: r[0], reverse=True)
    n = len(ordered)

    best_len = 0
    best_errors = 0
    wrong = 0
    for i, (_confidence, correct) in enumerate(ordered):
        if not correct:
            wrong += 1
        length = i + 1
        if wrong / length <= max_false_gap_rate:
            best_len = length
            best_errors = wrong

    coverage = best_len / n if n else 0.0
    false_gap_rate = best_errors / best_len if best_len else 0.0
    cutoff = ordered[best_len - 1][0] if best_len else 1.0
    return AbstentionPolicy(
        cutoff=cutoff,
        coverage=coverage,
        false_gap_rate=false_gap_rate,
        n_accepted=best_len,
    )
