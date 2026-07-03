"""Multi-class confusion matrix over absence verdicts (§25.15).

Distinct from the binary :mod:`kg_eval.confusion_matrix`: here the label space is a
finite set of *verdict* strings (``genuine_gap`` / ``possible_miss`` / ``retracted`` /
``abstain`` в каноническом порядке §15.10), and we build a full ``labels × labels``
count grid плюс per-label precision/recall/F1/support, а также overall accuracy и
macro-F1.

Label resolution: when ``labels`` не задан, берётся отсортированное объединение всех
наблюдаемых значений, но известные канонические verdict-метки выносятся вперёд в
фиксированном порядке (genuine_gap, possible_miss, retracted, abstain), а любые
дополнительные метки идут следом в алфавитном порядке.

Zero-denominator conventions: любой неопределённый коэффициент (метка ни разу не
предсказана / отсутствует в истине / поддержка ноль) сворачивается в ``0.0`` без
``ZeroDivisionError``. ``y_true`` и ``y_pred`` обязаны быть одной длины — иначе это
ошибка вызывающего, и поднимается ``ValueError``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical absence-verdict ordering (§15.10). Observed labels outside this set are
# appended afterwards in sorted order.
_CANONICAL_ORDER: tuple[str, ...] = (
    "genuine_gap",
    "possible_miss",
    "retracted",
    "abstain",
)


@dataclass(frozen=True)
class VerdictConfusion:
    """Multi-class confusion grid over verdict labels with derived metrics (§25.15).

    ``matrix[t][p]`` — количество примеров с истинной меткой ``t`` и предсказанной
    ``p``. ``per_label[label]`` содержит ``precision``/``recall``/``f1``/``support``.
    ``accuracy`` = доля верных (диагональ / всего); ``macro_f1`` = среднее F1 по меткам.
    """

    labels: list[str]
    matrix: dict[str, dict[str, int]]
    per_label: dict[str, dict[str, float]]
    accuracy: float
    macro_f1: float

    def as_dict(self) -> dict[str, object]:
        return {
            "labels": list(self.labels),
            "matrix": {t: dict(row) for t, row in self.matrix.items()},
            "per_label": {
                label: {k: round(v, 4) for k, v in stats.items()}
                for label, stats in self.per_label.items()
            },
            "accuracy": round(self.accuracy, 4),
            "macro_f1": round(self.macro_f1, 4),
        }


def _resolve_labels(observed: set[str], labels: list[str] | None) -> list[str]:
    """Resolve the ordered label list (canonical verdicts first, then extras)."""
    if labels is not None:
        return list(labels)
    canonical = [label for label in _CANONICAL_ORDER if label in observed]
    extras = sorted(observed - set(_CANONICAL_ORDER))
    return canonical + extras


def verdict_confusion(
    y_true: list[str],
    y_pred: list[str],
    *,
    labels: list[str] | None = None,
) -> VerdictConfusion:
    """Build a :class:`VerdictConfusion` from parallel truth/prediction sequences.

    Default ``labels`` — отсортированное объединение наблюдаемых значений с канонической
    verdict-меткой впереди. ``matrix[t][p]`` считает истину ``t`` при предсказании ``p``.
    Для каждой метки считаются precision/recall/f1/support; ``accuracy`` = trace/total;
    ``macro_f1`` = среднее f1. Разная длина входов поднимает ``ValueError``; любые
    нулевые знаменатели дают ``0.0``.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"y_true and y_pred length mismatch: {len(y_true)} != {len(y_pred)}")

    observed = set(y_true) | set(y_pred)
    resolved = _resolve_labels(observed, labels)
    label_set = set(resolved)

    matrix: dict[str, dict[str, int]] = {t: dict.fromkeys(resolved, 0) for t in resolved}
    for t, p in zip(y_true, y_pred, strict=True):
        # Only tally pairs whose labels are within the resolved space.
        if t in label_set and p in label_set:
            matrix[t][p] += 1

    total = len(y_true)
    trace = sum(matrix[label][label] for label in resolved)
    accuracy = trace / total if total else 0.0

    per_label: dict[str, dict[str, float]] = {}
    f1_scores: list[float] = []
    for label in resolved:
        tp = matrix[label][label]
        predicted = sum(matrix[t][label] for t in resolved)
        support = sum(matrix[label][p] for p in resolved)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(support),
        }
        f1_scores.append(f1)

    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    return VerdictConfusion(
        labels=resolved,
        matrix=matrix,
        per_label=per_label,
        accuracy=accuracy,
        macro_f1=macro_f1,
    )
