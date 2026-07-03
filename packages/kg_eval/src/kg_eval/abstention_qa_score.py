"""LitQA2-style scored QA with abstention (§23.31/§23.35).

Pure, deterministic scoring of an agentic QA system that may *abstain*
("unsure") instead of committing to an answer, following the LitQA2 protocol.
This is distinct from ``answerability_metrics.py``, which scores no-data
*verdicts* about whether the graph can answer a question — here we score answer
*correctness* under an abstention option ("уверенность против воздержания").

Each record is a mapping::

    {
        "predicted": "answer" | "unsure",  # committed an answer, or abstained
        "correct": bool,                    # was the committed answer correct?
    }

Only records with ``predicted == "answer"`` are *answered*; ``correct`` on an
``unsure`` record is ignored (an abstention is neither right nor wrong). The
LitQA2 protocol rewards being right when you commit and penalizes wrong
commits, while abstention is a soft escape hatch:

* ``precision`` — accuracy over *answered* records (``1.0`` when none answered),
* ``coverage`` — fraction of records that were answered,
* ``accuracy`` — fraction of *all* records answered correctly,
* ``litqa_score`` — ``precision * coverage`` (the combined LitQA2 score).

Because ``accuracy == precision * coverage`` and ``precision <= 1.0``, accuracy
can never exceed coverage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_ANSWER = "answer"


@dataclass(frozen=True)
class AbstentionScore:
    """LitQA2-style scores for a QA system with abstention (§23.31/§23.35).

    ``n`` total records, ``n_answered`` committed answers, ``n_correct`` correct
    commits. All four rates are floats in ``[0.0, 1.0]``; ``litqa_score`` is the
    combined ``precision * coverage`` LitQA2 score ("итоговый балл").
    """

    n: int
    n_answered: int
    n_correct: int
    precision: float
    coverage: float
    accuracy: float
    litqa_score: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "n": self.n,
            "n_answered": self.n_answered,
            "n_correct": self.n_correct,
            "precision": round(self.precision, 6),
            "coverage": round(self.coverage, 6),
            "accuracy": round(self.accuracy, 6),
            "litqa_score": round(self.litqa_score, 6),
        }


def score(records: Sequence[Mapping[str, object]]) -> AbstentionScore:
    """Score abstention-aware QA ``records`` under the LitQA2 protocol.

    Raises ``ValueError`` on empty input. A record is *answered* iff its
    ``predicted`` field equals ``"answer"``; a wrong answered record lowers
    ``precision`` below ``1.0``. Precision collapses to ``1.0`` when nothing is
    answered ("нет ответов — штрафа нет").
    """
    n = len(records)
    if n == 0:
        raise ValueError("score() requires at least one record / нужна хотя бы одна запись")

    n_answered = 0
    n_correct = 0
    for rec in records:
        if rec["predicted"] == _ANSWER:
            n_answered += 1
            if bool(rec["correct"]):
                n_correct += 1

    precision = n_correct / n_answered if n_answered else 1.0
    coverage = n_answered / n
    accuracy = n_correct / n
    litqa_score = precision * coverage
    return AbstentionScore(
        n=n,
        n_answered=n_answered,
        n_correct=n_correct,
        precision=precision,
        coverage=coverage,
        accuracy=accuracy,
        litqa_score=litqa_score,
    )
