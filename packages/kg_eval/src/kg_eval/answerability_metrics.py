"""No-data answerability scoring over labeled gap records (§25.15).

Pure, deterministic scoring of a gap/absence pipeline's per-question verdicts
against a gold ``no_data`` label. The point of this metric family is to check
that the system *flags* questions whose answer genuinely is not in the graph
("нет данных") without inventing spurious ``genuine_gap`` verdicts about
questions the graph *can* answer.

Each record is a mapping::

    {
        "predicted_verdict": one of
            {"genuine_gap", "possible_miss", "retracted", "abstain", "present"},
        "gold_no_data": bool,   # ground truth: answer is absent from the graph
        "intent": str,          # question intent; "competence_search" is dropped
    }

Records with intent ``competence_search`` describe "does the graph *cover* X"
probes rather than data-bearing questions, so they are dropped when
``data_bearing_only`` (the default) — they must not inflate or deflate the
no-data rates. A verdict counts as *flagged* when it is ``genuine_gap`` or
``possible_miss`` (both surface a candidate gap to the user).

Zero-denominator conventions: any undefined ratio (no gold-no-data records, no
flagged records, no data-bearing records) collapses to ``0.0`` — so empty input
yields all-zero metrics and ``n_evaluated == 0``.
"""

from __future__ import annotations

from dataclasses import dataclass

FLAGGED_VERDICTS = frozenset({"genuine_gap", "possible_miss"})
_COMPETENCE_INTENT = "competence_search"


@dataclass(frozen=True)
class AnswerabilityScores:
    """No-data answerability rates over labeled gap records (§25.15).

    All four rates are floats in ``[0.0, 1.0]``; ``n_evaluated`` is the number of
    records that survived intent filtering. ``support`` carries the raw counts
    (gold-no-data total, data-bearing total, flagged total) behind the rates.
    """

    no_data_recall: float
    no_data_precision: float
    false_gap_rate: float
    no_data_genuine_gap_rate: float
    n_evaluated: int
    support: dict[str, int]

    def as_dict(self) -> dict[str, float | int | dict[str, int]]:
        return {
            "no_data_recall": round(self.no_data_recall, 4),
            "no_data_precision": round(self.no_data_precision, 4),
            "false_gap_rate": round(self.false_gap_rate, 4),
            "no_data_genuine_gap_rate": round(self.no_data_genuine_gap_rate, 4),
            "n_evaluated": self.n_evaluated,
            "support": dict(self.support),
        }


def _is_flagged(verdict: str) -> bool:
    """A verdict *flags* a gap when it is ``genuine_gap`` or ``possible_miss``."""
    return verdict in FLAGGED_VERDICTS


def score_answerability(
    records: list[dict], *, data_bearing_only: bool = True
) -> AnswerabilityScores:
    """Score no-data answerability over labeled gap ``records`` (§25.15).

    When ``data_bearing_only`` (default), records whose ``intent`` is
    ``competence_search`` are dropped before any counting. All ratios use the
    ``0.0`` collapse on a zero denominator; ``n_evaluated`` reflects the count
    *after* filtering.
    """
    kept = [r for r in records if not (data_bearing_only and r.get("intent") == _COMPETENCE_INTENT)]

    gold_no_data = sum(1 for r in kept if r.get("gold_no_data"))
    data_bearing = sum(1 for r in kept if not r.get("gold_no_data"))
    flagged = sum(1 for r in kept if _is_flagged(str(r.get("predicted_verdict"))))

    nd_and_flagged = sum(
        1 for r in kept if r.get("gold_no_data") and _is_flagged(str(r.get("predicted_verdict")))
    )
    nd_and_genuine = sum(
        1 for r in kept if r.get("gold_no_data") and r.get("predicted_verdict") == "genuine_gap"
    )
    data_and_genuine = sum(
        1 for r in kept if not r.get("gold_no_data") and r.get("predicted_verdict") == "genuine_gap"
    )

    no_data_recall = nd_and_flagged / gold_no_data if gold_no_data else 0.0
    no_data_precision = nd_and_flagged / flagged if flagged else 0.0
    false_gap_rate = data_and_genuine / data_bearing if data_bearing else 0.0
    no_data_genuine_gap_rate = nd_and_genuine / gold_no_data if gold_no_data else 0.0

    support = {
        "gold_no_data": gold_no_data,
        "data_bearing": data_bearing,
        "flagged": flagged,
    }
    return AnswerabilityScores(
        no_data_recall=no_data_recall,
        no_data_precision=no_data_precision,
        false_gap_rate=false_gap_rate,
        no_data_genuine_gap_rate=no_data_genuine_gap_rate,
        n_evaluated=len(kept),
        support=support,
    )
