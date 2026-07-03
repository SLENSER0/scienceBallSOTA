"""Precision/recall golden regression for external-id -> canonical crosswalks (§20.13).

RU: Голден-регрессия маппинга ``external_id -> canonical`` с precision/recall.
EN: Compares a predicted ``(system, external_id) -> canonical`` crosswalk against a
frozen golden set, counting correct/wrong/missing and reporting precision & recall.

A case is keyed by ``(system, external_id)``. For each golden key: it is *correct*
when the predicted canonical matches, *missing* when the key is absent from the
predictions, and *wrong* when present but different (recorded as a mismatch tuple
``(key, expected, got)``). Precision is ``correct / len(predicted)`` and recall is
``correct / len(golden)`` (both ``0.0`` when their denominator is empty).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrosswalkGoldenResult:
    """RU: Итог голден-регрессии кросс-уолка. EN: Crosswalk golden regression result."""

    total: int
    correct: int
    wrong: int
    missing: int
    precision: float
    recall: float
    mismatches: tuple[tuple[tuple[str, str], str, str], ...]

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация в словарь. EN: Serialize to a plain dict."""
        return {
            "total": self.total,
            "correct": self.correct,
            "wrong": self.wrong,
            "missing": self.missing,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "mismatches": [[list(k), exp, got] for (k, exp, got) in self.mismatches],
        }


def evaluate_crosswalk(
    golden: dict[tuple[str, str], str],
    predicted: dict[tuple[str, str], str],
) -> CrosswalkGoldenResult:
    """RU: Оценить предсказанный кросс-уолк. EN: Evaluate a predicted crosswalk.

    Both maps are keyed by ``(system, external_id)``. For every golden key the
    prediction is *correct* (equal canonical), *missing* (key absent) or *wrong*
    (present but different). ``precision = correct / len(predicted)`` and
    ``recall = correct / len(golden)`` (``0.0`` when the denominator is empty).
    """
    total = len(golden)
    correct = 0
    wrong = 0
    missing = 0
    mismatches: list[tuple[tuple[str, str], str, str]] = []
    for key, expected in golden.items():
        if key not in predicted:
            missing += 1
            continue
        got = predicted[key]
        if got == expected:
            correct += 1
        else:
            wrong += 1
            mismatches.append((key, expected, got))
    precision = correct / len(predicted) if predicted else 0.0
    recall = correct / total if total else 0.0
    return CrosswalkGoldenResult(
        total=total,
        correct=correct,
        wrong=wrong,
        missing=missing,
        precision=precision,
        recall=recall,
        mismatches=tuple(mismatches),
    )
