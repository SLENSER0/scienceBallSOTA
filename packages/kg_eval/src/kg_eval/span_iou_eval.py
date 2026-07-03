"""Extraction span-accuracy via char-offset IoU span-set matching (§6.17).

``extraction_recall_eval`` матчит факты только по равенству ``fact_id``; §6.17 требует
*span-accuracy* — точности границ извлечённого фрагмента через IoU (intersection-over-union)
символьных смещений. Пара «предсказанный/золотой» спан считается совпавшей, если её IoU не
ниже порога (по умолчанию ``0.5``; §6.17 рекомендует ``>=0.9`` для «точных» границ).

Span model: a span is a half-open char range ``(start, end)`` with ``start <= end``. IoU is
``intersection / union`` of the two ranges (``0.0`` when they do not overlap, ``1.0`` when
identical). :func:`match_spans` does greedy one-to-one matching: it ranks every candidate
pred/gold pair by IoU (descending), then consumes pairs above ``threshold`` such that each
pred and each gold is used at most once. Matched pairs are ``tp``; unmatched preds are ``fp``;
unmatched golds are ``fn``. ``mean_iou`` averages IoU over the matched (``tp``) pairs only
(``0.0`` when there is no match).
"""

from __future__ import annotations

from dataclasses import dataclass

Span = tuple[int, int]


def span_iou(a: Span, b: Span) -> float:
    """IoU (пересечение/объединение) двух полу-открытых символьных диапазонов.

    ``a`` и ``b`` — пары ``(start, end)`` с ``start <= end``. Возвращает ``0.0`` при
    отсутствии пересечения (или нулевом объединении) и ``1.0`` для идентичных диапазонов.
    """
    a_start, a_end = a
    b_start, b_end = b
    inter = min(a_end, b_end) - max(a_start, b_start)
    if inter <= 0:
        return 0.0
    union = max(a_end, b_end) - min(a_start, b_start)
    if union <= 0:
        return 0.0
    return inter / union


@dataclass(frozen=True)
class SpanEvalResult:
    """Span-set matching result at a fixed IoU threshold (§6.17).

    ``tp``/``fp``/``fn`` — совпавшие пары / лишние предсказания / пропущенные золотые спаны.
    ``precision``/``recall``/``f1`` в ``[0.0, 1.0]``; ``mean_iou`` — средний IoU по совпавшим
    парам (``0.0`` без совпадений).
    """

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    mean_iou: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "mean_iou": round(self.mean_iou, 4),
        }


def match_spans(pred: list[Span], gold: list[Span], threshold: float = 0.5) -> SpanEvalResult:
    """Greedy one-to-one IoU matching of predicted vs gold spans (§6.17).

    Все пары ``(i, j)`` ранжируются по убыванию IoU; жадно берутся пары с IoU ``>= threshold``,
    пока каждый ``pred``/``gold`` не использован более одного раза. Совпадения — ``tp``, лишние
    предсказания — ``fp``, непокрытые золотые — ``fn``.
    """
    candidates: list[tuple[float, int, int]] = []
    for i, p in enumerate(pred):
        for j, g in enumerate(gold):
            iou = span_iou(p, g)
            if iou >= threshold and iou > 0.0:
                candidates.append((iou, i, j))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))

    used_pred: set[int] = set()
    used_gold: set[int] = set()
    matched_ious: list[float] = []
    for iou, i, j in candidates:
        if i in used_pred or j in used_gold:
            continue
        used_pred.add(i)
        used_gold.add(j)
        matched_ious.append(iou)

    tp = len(matched_ious)
    fp = len(pred) - tp
    fn = len(gold) - tp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    mean_iou = sum(matched_ious) / tp if tp > 0 else 0.0
    return SpanEvalResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_iou=mean_iou,
    )
