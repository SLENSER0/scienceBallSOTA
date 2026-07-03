"""HalluMat prevalence-weighted Hallucination-Contradiction Score (§23.35).

Pure, deterministic scoring of a QA/RAG system over ``HalluMatData``-style
records, where each query carries two independent factuality flags plus a
*prevalence* weight expressing how common or important that query type is
("распространённость запроса"). The Prevalence-weighted Hallucination-
Contradiction Score (PHCS) aggregates hallucination and contradiction rates,
weighting each query by its prevalence so that frequent/important query types
dominate the score.

Each record is a mapping::

    {
        "hallucinated": bool,   # answer asserts unsupported facts
        "contradicted": bool,   # answer contradicts the evidence
        "prevalence": float,    # weight >= 0.0, defaults to 1.0
    }

Given ``alpha`` in ``[0, 1]`` blending the two failure modes::

    hallucination_prevalence = sum(prev * hallucinated) / sum(prev)
    contradiction_prevalence = sum(prev * contradicted) / sum(prev)
    phcs = 1 - (alpha * hallucination_prevalence
                + (1 - alpha) * contradiction_prevalence)

so a system with no failures scores ``1.0`` and one that always both
hallucinates and contradicts scores ``0.0``. ``passed`` is ``phcs >= gate``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_HALLUCINATED = "hallucinated"
_CONTRADICTED = "contradicted"
_PREVALENCE = "prevalence"


@dataclass(frozen=True)
class PHCSReport:
    """Prevalence-weighted Hallucination-Contradiction Score (§23.35).

    ``n`` records, ``total_prevalence`` the summed weights, and the two
    prevalence-weighted failure rates in ``[0.0, 1.0]``. ``phcs`` is the
    combined score ("итоговый балл"); ``passed`` is ``phcs >= gate``.
    """

    n: int
    total_prevalence: float
    hallucination_prevalence: float
    contradiction_prevalence: float
    phcs: float
    passed: bool

    def as_dict(self) -> dict[str, int | float | bool]:
        return {
            "n": self.n,
            "total_prevalence": round(self.total_prevalence, 6),
            "hallucination_prevalence": round(self.hallucination_prevalence, 6),
            "contradiction_prevalence": round(self.contradiction_prevalence, 6),
            "phcs": round(self.phcs, 6),
            "passed": self.passed,
        }


def score_phcs(
    records: Sequence[Mapping[str, object]],
    *,
    alpha: float = 0.5,
    gate: float = 0.8,
) -> PHCSReport:
    """Compute the PHCS over prevalence-weighted HalluMat ``records``.

    ``alpha`` blends hallucination vs. contradiction prevalence; ``gate`` is the
    pass threshold. Raises ``ValueError`` on empty input or on any negative
    prevalence ("отрицательная распространённость недопустима"). A missing
    ``prevalence`` field defaults to ``1.0``.
    """
    n = len(records)
    if n == 0:
        raise ValueError("score_phcs() requires at least one record / нужна хотя бы одна запись")

    total_prevalence = 0.0
    hallucinated_weight = 0.0
    contradicted_weight = 0.0
    for rec in records:
        prevalence = float(rec.get(_PREVALENCE, 1.0))
        if prevalence < 0.0:
            raise ValueError(
                "prevalence must be non-negative / распространённость должна быть неотрицательной"
            )
        total_prevalence += prevalence
        if bool(rec[_HALLUCINATED]):
            hallucinated_weight += prevalence
        if bool(rec[_CONTRADICTED]):
            contradicted_weight += prevalence

    if total_prevalence == 0.0:
        raise ValueError(
            "total prevalence must be positive / суммарная распространённость должна быть > 0"
        )

    hallucination_prevalence = hallucinated_weight / total_prevalence
    contradiction_prevalence = contradicted_weight / total_prevalence
    phcs = 1.0 - (alpha * hallucination_prevalence + (1.0 - alpha) * contradiction_prevalence)
    passed = phcs >= gate
    return PHCSReport(
        n=n,
        total_prevalence=total_prevalence,
        hallucination_prevalence=hallucination_prevalence,
        contradiction_prevalence=contradiction_prevalence,
        phcs=phcs,
        passed=passed,
    )
