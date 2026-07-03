"""Golden regression evaluator for external_id->canonical crosswalks (§20.13).

RU: Голден-регрессия для маппинга ``external_id -> canonical`` кросс-уолка.
EN: Compares predicted ``(system, external_id) -> canonical`` mappings against a
frozen golden set, counting correct/incorrect/missing and reporting accuracy.

A case is keyed by ``(system, external_id)``. If the key is absent from the
predictions it is *missing*; if present and equal to the expected canonical it is
*correct*; otherwise it is *incorrect* and recorded as a mismatch tuple
``(external_id, expected, got)``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CrosswalkGoldenCase:
    """RU: Один эталонный случай. EN: One golden crosswalk case."""

    system: str
    external_id: str
    expected_canonical: str

    def as_dict(self) -> dict[str, str]:
        return {
            "system": self.system,
            "external_id": self.external_id,
            "expected_canonical": self.expected_canonical,
        }


@dataclass(frozen=True)
class CrosswalkGoldenReport:
    """RU: Итог регрессии. EN: Aggregate crosswalk regression report."""

    total: int
    correct: int
    incorrect: int
    missing: int
    accuracy: float
    mismatches: tuple[tuple[str, str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "missing": self.missing,
            "accuracy": round(self.accuracy, 6),
            "mismatches": [list(m) for m in self.mismatches],
        }


def evaluate_crosswalk(
    cases: Iterable[CrosswalkGoldenCase],
    predicted: Mapping[tuple[str, str], str],
) -> CrosswalkGoldenReport:
    """RU: Оценить предсказанный кросс-уолк. EN: Evaluate a predicted crosswalk.

    ``predicted`` is keyed by ``(system, external_id)``. Missing keys count as
    *missing* (not incorrect); accuracy is ``correct / total`` (0.0 if empty).
    """
    total = 0
    correct = 0
    incorrect = 0
    missing = 0
    mismatches: list[tuple[str, str, str]] = []
    for case in cases:
        total += 1
        key = (case.system, case.external_id)
        if key not in predicted:
            missing += 1
            continue
        got = predicted[key]
        if got == case.expected_canonical:
            correct += 1
        else:
            incorrect += 1
            mismatches.append((case.external_id, case.expected_canonical, got))
    accuracy = correct / total if total else 0.0
    return CrosswalkGoldenReport(
        total=total,
        correct=correct,
        incorrect=incorrect,
        missing=missing,
        accuracy=accuracy,
        mismatches=tuple(mismatches),
    )
