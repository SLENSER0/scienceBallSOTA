"""Golden QA runner + scoring (§18.9).

Прогоняет «золотой» набор вопросов-ответов (:class:`~kg_eval.golden_builder.GoldenQA`,
модуль читаем и НЕ редактируем) через любую функцию-ответчик и считает три
детерминированные метрики: полноту сущностей (entity recall), долю попаданий по
подстрокам ответа (answer hit rate) и точность предсказания пробелов знаний
(gap precision). Чистый python — ни графа, ни хранилища, ни LLM: ``answer_fn``
инкапсулирует всю систему и вызывается как ``answer_fn(question) -> {entities,
answer, gap}``.

Runs a golden QA set through any answer function and scores three deterministic
metrics — entity recall, answer-substring hit rate and gap-prediction precision —
returning a frozen :class:`GoldenReport`. Pure python: ``answer_fn(question)``
returns ``{"entities": list, "answer": str, "gap": bool}`` and hides the system
under test, so no store/graph/LLM is imported here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from kg_eval.golden_builder import GoldenQA

# answer_fn(question) -> {"entities": list, "answer": str, "gap": bool}
AnswerFn = Callable[[str], Mapping[str, object]]


@dataclass(frozen=True)
class ItemScore:
    """Оценка одного кейса / one scored golden item (§18.9).

    ``id``            — идентификатор исходного :class:`GoldenQA`.
    ``entity_recall`` — доля ожидаемых сущностей, найденных в ответе [0, 1].
    ``answer_hit``    — все ли ожидаемые подстроки присутствуют в ответе.
    ``predicted_gap`` — сообщил ли ответчик о пробеле знаний.
    ``expected_gap``  — ожидался ли пробел по «золотому» кейсу.
    ``gap_match``     — совпало ли предсказание пробела с ожиданием.
    """

    id: str
    entity_recall: float
    answer_hit: bool
    predicted_gap: bool
    expected_gap: bool
    gap_match: bool

    def as_dict(self) -> dict[str, object]:
        """Serialise to a plain JSON-friendly dict (rounded recall)."""
        return {
            "id": self.id,
            "entity_recall": round(self.entity_recall, 4),
            "answer_hit": self.answer_hit,
            "predicted_gap": self.predicted_gap,
            "expected_gap": self.expected_gap,
            "gap_match": self.gap_match,
        }


@dataclass(frozen=True)
class GoldenReport:
    """Свод по прогону «золотого» набора / golden-run summary (§18.9).

    ``n``               — число оценённых кейсов.
    ``entity_recall``   — средняя полнота сущностей по кейсам [0, 1].
    ``answer_hit_rate`` — доля кейсов, где ответ содержит все подстроки [0, 1].
    ``gap_precision``   — точность предсказания пробелов TP/(TP+FP) [0, 1].
    ``per_item``        — покейсовые оценки в исходном порядке набора.
    """

    n: int
    entity_recall: float
    answer_hit_rate: float
    gap_precision: float
    per_item: tuple[ItemScore, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Plain-``dict`` view (JSON-ready); ``per_item`` becomes a list of dicts."""
        return {
            "n": self.n,
            "entity_recall": round(self.entity_recall, 4),
            "answer_hit_rate": round(self.answer_hit_rate, 4),
            "gap_precision": round(self.gap_precision, 4),
            "per_item": [item.as_dict() for item in self.per_item],
        }


def _entity_recall(expected: tuple[str, ...], predicted: object) -> float:
    """Recall of ``expected`` seed-ids within a predicted entity list [0, 1].

    Пустой список ожидаемых сущностей → полнота 1.0 (нечего пропускать); иначе
    доля попавших. An empty expectation scores a vacuous 1.0.
    """
    if not expected:
        return 1.0
    got = {str(e) for e in predicted} if isinstance(predicted, (list, tuple, set)) else set()
    hit = sum(1 for e in expected if e in got)
    return hit / len(expected)


def _answer_hit(expected_substrings: tuple[str, ...], answer: str) -> bool:
    """True iff every expected substring appears in ``answer`` (vacuous on empty)."""
    return all(sub in answer for sub in expected_substrings)


def _gap_precision(scores: Sequence[ItemScore]) -> float:
    """Precision of gap predictions: TP/(TP+FP); 0.0 when nothing was predicted.

    Пробел считается верным (TP), когда предсказан и ожидался; ложным (FP), когда
    предсказан, но не ожидался. Без единого предсказания точность 0.0 — типичная
    для sklearn договорённость (нет положительных предсказаний → 0).
    """
    tp = sum(1 for s in scores if s.predicted_gap and s.expected_gap)
    fp = sum(1 for s in scores if s.predicted_gap and not s.expected_gap)
    denom = tp + fp
    return tp / denom if denom else 0.0


def run_golden(golden: Sequence[GoldenQA], answer_fn: AnswerFn) -> GoldenReport:
    """Run every :class:`GoldenQA` through ``answer_fn`` and score it (§18.9).

    Для каждого кейса вызывает ``answer_fn(question)`` и получает
    ``{"entities": list, "answer": str, "gap": bool}``, затем считает полноту
    сущностей, попадание по подстрокам ответа и совпадение пробела. Итоговые
    агрегаты — среднее по кейсам (полнота/попадания) и точность пробелов;
    пустой набор → нулевой :class:`GoldenReport`.

    Runs each golden question through ``answer_fn`` and aggregates the three
    metrics into a frozen :class:`GoldenReport`. Deterministic and store-free.
    """
    scores: list[ItemScore] = []
    for qa in golden:
        result = answer_fn(qa.question)
        entities = result.get("entities", [])
        answer = str(result.get("answer", "") or "")
        predicted_gap = bool(result.get("gap", False))
        scores.append(
            ItemScore(
                id=qa.id,
                entity_recall=_entity_recall(qa.expected_entities, entities),
                answer_hit=_answer_hit(qa.expected_answer_contains, answer),
                predicted_gap=predicted_gap,
                expected_gap=qa.expected_gap,
                gap_match=predicted_gap == qa.expected_gap,
            )
        )

    n = len(scores)
    entity_recall = sum(s.entity_recall for s in scores) / n if n else 0.0
    answer_hit_rate = sum(1 for s in scores if s.answer_hit) / n if n else 0.0
    gap_precision = _gap_precision(scores)
    return GoldenReport(
        n=n,
        entity_recall=entity_recall,
        answer_hit_rate=answer_hit_rate,
        gap_precision=gap_precision,
        per_item=tuple(scores),
    )


__all__ = [
    "AnswerFn",
    "GoldenReport",
    "ItemScore",
    "run_golden",
]
