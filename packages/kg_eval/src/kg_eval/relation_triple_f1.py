"""Typed (subject, relation, object) triple-extraction P/R/F1, micro + macro (§23.35).

Scores *relation extraction* in the SciNLP/MatSciNLP sense: the unit is a typed triple
``(subject, relation, object)``, and a predicted triple is correct only when all three
slots match a gold triple after case/space normalisation. This is deliberately distinct
from ``extraction_recall_eval.py`` (matches on an opaque ``fact_id`` set, with no relation
typing at all) and from ``entity_linking_eval.py`` (ranks KB candidates for a single
mention). Here the relation label is first-class: we report both a *micro* score over all
triples and a *macro* score as the unweighted mean of per-relation F1.

Модель сопоставления. Каждая сторона (gold / predicted) сворачивается в множество
нормализованных троек — дубликаты схлопываются, так что один и тот же предсказанный
триплет не может дать два true-positive. Нормализация применяется ко всем трём слотам:
регистр приводится к нижнему, окружающие пробелы срезаются. Триплет считается совпавшим
тогда и только тогда, когда нормализованная тройка присутствует в обоих множествах.

Метрики. Micro-precision/recall/F1 считаются по всем триплетам сразу (TP/FP/FN —
глобальные счётчики). Macro-F1 — среднее арифметическое F1 по каждой релации, встречающейся
в gold или predicted (невзвешенное, поэтому редкая релация весит столько же, сколько
частая). Любое отношение с нулевым знаменателем даёт ``0.0`` по конвенции.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

Triple = tuple[str, str, str]


def normalize_triple(triple: Triple) -> Triple:
    """Normalise all three slots case/space-insensitively.

    Каждый слот приводится к нижнему регистру и обрезается по краям от пробелов, так что
    ``('Al', 'has_property', 'ductile')`` и ``('al', 'HAS_PROPERTY', 'Ductile')`` дают
    одну и ту же каноническую тройку.
    """
    subject, relation, obj = triple
    return (subject.strip().lower(), relation.strip().lower(), obj.strip().lower())


def _ratio(numerator: int, denominator: int) -> float:
    """Safe ratio: ``0.0`` when the denominator is zero (nothing to divide)."""
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    """Harmonic mean of precision and recall; ``0.0`` when both are zero."""
    denominator = precision + recall
    return 2 * precision * recall / denominator if denominator else 0.0


@dataclass(frozen=True)
class RelScore:
    """Per-relation confusion counts and derived P/R/F1 (§23.35).

    ``tp``/``fp``/``fn`` — точные целые счётчики совпавших / лишних / пропущенных троек
    для одной релации; ``precision``/``recall``/``f1`` — доли в ``[0.0, 1.0]`` (``0.0``
    при нулевом знаменателе).
    """

    relation: str
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, str | int | float]:
        """Serialise: integer counts exact, float ratios rounded to 4 dp."""
        return {
            "relation": self.relation,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass(frozen=True)
class TripleF1Report:
    """Micro + macro triple-extraction report with per-relation breakdown (§23.35).

    ``micro_*`` — метрики по всем триплетам сразу; ``macro_f1`` — невзвешенное среднее
    ``f1`` по релациям в ``by_relation``; ``by_relation`` отсортирован по имени релации.
    """

    micro_precision: float
    micro_recall: float
    micro_f1: float
    macro_f1: float
    by_relation: tuple[RelScore, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "micro_precision": round(self.micro_precision, 4),
            "micro_recall": round(self.micro_recall, 4),
            "micro_f1": round(self.micro_f1, 4),
            "macro_f1": round(self.macro_f1, 4),
            "by_relation": [r.as_dict() for r in self.by_relation],
        }


def score_triples(gold: Iterable[Triple], predicted: Iterable[Triple]) -> TripleF1Report:
    """Score typed triple extraction of ``predicted`` against ``gold`` (§23.35).

    Обе стороны нормализуются и сворачиваются в множества, поэтому дубликаты схлопываются
    (никакого двойного TP). Триплет совпал, если он есть в обоих множествах. Micro-метрики
    считаются по всем триплетам; macro-F1 — среднее F1 по каждой релации, присутствующей в
    gold или predicted. Все отношения с нулевым знаменателем дают ``0.0``.
    """
    gold_set = {normalize_triple(t) for t in gold}
    pred_set = {normalize_triple(t) for t in predicted}

    matched = gold_set & pred_set
    tp_total = len(matched)
    fp_total = len(pred_set - gold_set)
    fn_total = len(gold_set - pred_set)

    per_tp: dict[str, int] = defaultdict(int)
    per_fp: dict[str, int] = defaultdict(int)
    per_fn: dict[str, int] = defaultdict(int)
    for _subject, relation, _obj in matched:
        per_tp[relation] += 1
    for _subject, relation, _obj in pred_set - gold_set:
        per_fp[relation] += 1
    for _subject, relation, _obj in gold_set - pred_set:
        per_fn[relation] += 1

    relations = sorted(set(per_tp) | set(per_fp) | set(per_fn))
    by_relation: list[RelScore] = []
    f1_values: list[float] = []
    for relation in relations:
        tp, fp, fn = per_tp[relation], per_fp[relation], per_fn[relation]
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = _f1(precision, recall)
        by_relation.append(RelScore(relation, tp, fp, fn, precision, recall, f1))
        f1_values.append(f1)

    micro_precision = _ratio(tp_total, tp_total + fp_total)
    micro_recall = _ratio(tp_total, tp_total + fn_total)
    micro_f1 = _f1(micro_precision, micro_recall)
    macro_f1 = sum(f1_values) / len(f1_values) if f1_values else 0.0

    return TripleF1Report(
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=micro_f1,
        macro_f1=macro_f1,
        by_relation=tuple(by_relation),
    )
