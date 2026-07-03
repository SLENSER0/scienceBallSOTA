"""Contradiction-resolution pick accuracy for the §15.4 source-quality heuristic (§18.8).

When two measurements disagree, the §15.4 source-quality heuristic marks one side as
``likely_correct_measurement_id`` — a *prediction* about which measurement to trust
(«какое измерение вероятно верно»). This module scores that prediction against a
golden ``correct_measurement_id`` per contradiction, measuring how often the heuristic
picks the right side.

Each record is a mapping::

    {
        "predicted_id": str | None,  # likely_correct_measurement_id, or None to abstain
        "gold_id": str,              # correct_measurement_id (ground truth)
    }

A ``None`` or empty ``predicted_id`` counts as an *abstention* — the heuristic declined
to break the tie — and is excluded from the accuracy denominator, never counted as a
wrong pick («воздержание — не ошибка»). Ids are compared by ``str`` so a predicted id
that matches gold under differing string-like types still resolves as correct.

* ``n_scored``  — non-abstaining records (the accuracy denominator),
* ``n_abstained`` — records with a None/empty prediction,
* ``accuracy``  — ``correct / n_scored`` (``0.0`` when nothing was scored),
* ``coverage``  — ``n_scored / total`` (abstentions counted in the denominator).

This is distinct from ``abstention_qa_score.py`` (LitQA2 answer correctness): here the
unit is a *contradiction* and the abstention signal is a missing predicted id rather
than an explicit "unsure" label.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolutionScore:
    """Pick accuracy for §15.4 contradiction resolution (§18.8).

    ``n_scored`` non-abstaining picks, ``n_abstained`` skipped contradictions.
    ``accuracy`` is over scored picks only; ``coverage`` counts abstentions in its
    denominator, so ``coverage`` falls as the heuristic abstains more.
    """

    accuracy: float
    n_scored: int
    n_abstained: int
    coverage: float

    def as_dict(self) -> dict[str, int | float]:
        """Serialise: integer counts exact, float ratios rounded to 6 dp."""
        return {
            "accuracy": round(self.accuracy, 6),
            "n_scored": self.n_scored,
            "n_abstained": self.n_abstained,
            "coverage": round(self.coverage, 6),
        }


def _is_abstention(predicted_id: object) -> bool:
    """A None or empty (empty-string) predicted id is an abstention."""
    return predicted_id is None or (isinstance(predicted_id, str) and predicted_id == "")


def evaluate_resolutions(records: Sequence[Mapping[str, object]]) -> ResolutionScore:
    """Score §15.4 likely-correct picks against golden ids (§18.8).

    Each record carries ``predicted_id`` (the heuristic's pick, or None/empty to
    abstain) and ``gold_id`` (ground truth). Abstentions are excluded from the
    accuracy denominator but still counted in ``coverage``. Empty input yields an
    all-zero score; ``accuracy`` and ``coverage`` collapse to ``0.0`` when nothing is
    scored (no ``ZeroDivisionError``). Ids are compared by ``str``.
    """
    total = len(records)
    n_scored = 0
    n_correct = 0
    n_abstained = 0
    for rec in records:
        predicted_id = rec.get("predicted_id")
        if _is_abstention(predicted_id):
            n_abstained += 1
            continue
        n_scored += 1
        if str(predicted_id) == str(rec.get("gold_id")):
            n_correct += 1

    accuracy = n_correct / n_scored if n_scored else 0.0
    coverage = n_scored / total if total else 0.0
    return ResolutionScore(
        accuracy=accuracy,
        n_scored=n_scored,
        n_abstained=n_abstained,
        coverage=coverage,
    )
