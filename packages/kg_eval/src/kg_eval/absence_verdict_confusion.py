"""Verdict-aware confusion matrix for the four absence verdicts (§25.11/§25.15).

Unlike the generic binary :mod:`kg_eval.confusion_matrix` (§18.11), this module is
*verdict-aware*: it scores the four-way absence-claim decision defined in §25.11/§25.15
— ``genuine_gap`` (подтверждённый пробел), ``possible_miss`` (возможный пропуск),
``retracted`` (отозвано) и ``abstain`` (воздержаться). Each ``(gold, predicted)`` pair
lands in one cell of a full 4×4 grid, and per-verdict precision/recall/F1 are derived
in the usual one-vs-rest way.

Zero-denominator conventions: любое неопределённое отношение (verdict never predicted,
verdict never present, empty inputs) collapses to ``0.0`` — so an unseen verdict yields
``support == 0`` with ``precision == recall == f1 == 0.0`` and never divides by zero.
"""

from __future__ import annotations

from dataclasses import dataclass

VERDICTS: tuple[str, ...] = ("genuine_gap", "possible_miss", "retracted", "abstain")
"""Canonical absence verdicts in stable order (§25.11/§25.15)."""


@dataclass(frozen=True)
class VerdictConfusion:
    """Four-way verdict confusion grid with per-verdict metrics (§25.15).

    ``matrix[gold][pred]`` counts pairs whose gold verdict is ``gold`` and predicted
    verdict is ``pred``. ``per_verdict[v]`` holds ``{'precision', 'recall', 'f1',
    'support'}`` (one-vs-rest, floats in ``[0.0, 1.0]``; ``support`` — целое число gold
    примеров как float). ``accuracy`` — доля пар на диагонали; ``support`` — общее число
    оценённых пар.
    """

    matrix: dict[str, dict[str, int]]
    per_verdict: dict[str, dict[str, float]]
    accuracy: float
    support: int

    def as_dict(self) -> dict[str, object]:
        """Serialise to plain nested dicts (JSON-friendly)."""
        return {
            "matrix": {gold: dict(row) for gold, row in self.matrix.items()},
            "per_verdict": {v: dict(stats) for v, stats in self.per_verdict.items()},
            "accuracy": round(self.accuracy, 4),
            "support": self.support,
        }


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Return ``numerator / denominator`` or ``0.0`` when the denominator is zero."""
    return numerator / denominator if denominator else 0.0


def build_verdict_confusion(pairs: list[tuple[str, str]]) -> VerdictConfusion:
    """Build a :class:`VerdictConfusion` from ``(gold, predicted)`` verdict pairs.

    The grid always spans every verdict in :data:`VERDICTS`; any additional labels seen
    in ``pairs`` are appended (sorted) so no observation is silently dropped. Accuracy is
    the fraction of pairs on the diagonal; per-verdict precision/recall/F1 use one-vs-rest
    counts with :func:`_safe_ratio` guarding every division.
    """
    labels: list[str] = list(VERDICTS)
    for gold, pred in pairs:
        for label in (gold, pred):
            if label not in labels:
                labels.append(label)
    extra = sorted(label for label in labels if label not in VERDICTS)
    labels = list(VERDICTS) + extra

    matrix: dict[str, dict[str, int]] = {g: dict.fromkeys(labels, 0) for g in labels}
    for gold, pred in pairs:
        matrix[gold][pred] += 1

    support = len(pairs)
    correct = sum(matrix[v][v] for v in labels)
    accuracy = _safe_ratio(correct, support)

    per_verdict: dict[str, dict[str, float]] = {}
    for v in labels:
        tp = matrix[v][v]
        gold_total = sum(matrix[v][p] for p in labels)  # tp + fn
        pred_total = sum(matrix[g][v] for g in labels)  # tp + fp
        precision = _safe_ratio(tp, pred_total)
        recall = _safe_ratio(tp, gold_total)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        per_verdict[v] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(gold_total),
        }

    return VerdictConfusion(
        matrix=matrix,
        per_verdict=per_verdict,
        accuracy=accuracy,
        support=support,
    )
