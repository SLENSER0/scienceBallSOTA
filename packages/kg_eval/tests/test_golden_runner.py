"""Golden QA runner + scoring tests (§18.9).

Использует детерминированные stub-функции-ответчики (без графа/LLM), поэтому все
метрики проверяемы вручную. Uses deterministic stub answer functions so every
metric can be hand-checked.
"""

from __future__ import annotations

from collections.abc import Mapping

from kg_eval.golden_builder import GoldenQA
from kg_eval.golden_runner import GoldenReport, ItemScore, run_golden

# --- Small hand-checkable golden set ----------------------------------------
# Два кейса с сущностями/подстроками и один явный «пробел». Порядок фиксирован.
_GOLDEN: tuple[GoldenQA, ...] = (
    GoldenQA(
        id="q_ro",
        question="Обратный осмос?",
        expected_entities=("reverse_osmosis", "tds"),
        expected_answer_contains=("осмос", "мембран"),
        expected_gap=False,
    ),
    GoldenQA(
        id="q_so2",
        question="Удаление SO2?",
        expected_entities=("so2_removal",),
        expected_answer_contains=("SO2",),
        expected_gap=False,
    ),
    GoldenQA(
        id="q_gap",
        question="Есть ли эксперименты для холодного кучного выщелачивания?",
        expected_entities=("heap_leaching",),
        expected_answer_contains=("нет данных",),
        expected_gap=True,
    ),
)


def _perfect_fn(golden: tuple[GoldenQA, ...]) -> object:
    """Build an answer_fn that returns exactly what each golden case expects."""
    by_q = {qa.question: qa for qa in golden}

    def answer_fn(question: str) -> Mapping[str, object]:
        qa = by_q[question]
        return {
            "entities": list(qa.expected_entities),
            "answer": " ".join(qa.expected_answer_contains) or "ok",
            "gap": qa.expected_gap,
        }

    return answer_fn


def test_perfect_answers_score_recall_and_hit_one() -> None:
    report = run_golden(_GOLDEN, _perfect_fn(_GOLDEN))
    assert report.n == 3
    assert report.entity_recall == 1.0
    assert report.answer_hit_rate == 1.0
    # The single expected gap is predicted with no false positives → precision 1.0.
    assert report.gap_precision == 1.0


def test_entity_miss_lowers_recall() -> None:
    def answer_fn(question: str) -> Mapping[str, object]:
        # q_ro loses one of its two expected entities → item recall 0.5.
        if question == "Обратный осмос?":
            return {"entities": ["reverse_osmosis"], "answer": "осмос мембран", "gap": False}
        qa = {q.question: q for q in _GOLDEN}[question]
        return {
            "entities": list(qa.expected_entities),
            "answer": " ".join(qa.expected_answer_contains) or "ok",
            "gap": qa.expected_gap,
        }

    report = run_golden(_GOLDEN, answer_fn)
    # Per-item recalls: 0.5, 1.0, 1.0 → mean 2.5/3.
    assert report.entity_recall < 1.0
    assert abs(report.entity_recall - (2.5 / 3.0)) < 1e-9
    by_id = {it.id: it for it in report.per_item}
    assert by_id["q_ro"].entity_recall == 0.5


def test_answer_substring_miss_lowers_hit_rate() -> None:
    def answer_fn(question: str) -> Mapping[str, object]:
        # q_so2 answer omits the required "SO2" substring → that item does not hit.
        if question == "Удаление SO2?":
            return {"entities": ["so2_removal"], "answer": "десульфуризация", "gap": False}
        qa = {q.question: q for q in _GOLDEN}[question]
        return {
            "entities": list(qa.expected_entities),
            "answer": " ".join(qa.expected_answer_contains) or "ok",
            "gap": qa.expected_gap,
        }

    report = run_golden(_GOLDEN, answer_fn)
    # Two of three items hit their substrings → 2/3.
    assert abs(report.answer_hit_rate - (2.0 / 3.0)) < 1e-9
    by_id = {it.id: it for it in report.per_item}
    assert by_id["q_so2"].answer_hit is False
    assert by_id["q_ro"].answer_hit is True


def test_gap_match_scored_per_item_and_precision() -> None:
    report = run_golden(_GOLDEN, _perfect_fn(_GOLDEN))
    by_id = {it.id: it for it in report.per_item}
    assert by_id["q_gap"].predicted_gap is True
    assert by_id["q_gap"].expected_gap is True
    assert by_id["q_gap"].gap_match is True
    assert by_id["q_ro"].predicted_gap is False
    assert by_id["q_ro"].gap_match is True
    assert report.gap_precision == 1.0


def test_gap_false_positive_lowers_precision() -> None:
    def answer_fn(question: str) -> Mapping[str, object]:
        # q_ro wrongly flags a gap (false positive); the true gap is also found.
        qa = {q.question: q for q in _GOLDEN}[question]
        gap = True if qa.id in ("q_ro", "q_gap") else qa.expected_gap
        return {
            "entities": list(qa.expected_entities),
            "answer": " ".join(qa.expected_answer_contains) or "ok",
            "gap": gap,
        }

    report = run_golden(_GOLDEN, answer_fn)
    # TP=1 (q_gap), FP=1 (q_ro) → precision 0.5.
    assert report.gap_precision == 0.5
    by_id = {it.id: it for it in report.per_item}
    assert by_id["q_ro"].gap_match is False


def test_per_item_length_equals_n() -> None:
    report = run_golden(_GOLDEN, _perfect_fn(_GOLDEN))
    assert len(report.per_item) == report.n == len(_GOLDEN)
    assert all(isinstance(it, ItemScore) for it in report.per_item)
    # Order is preserved from the input golden set.
    assert [it.id for it in report.per_item] == [qa.id for qa in _GOLDEN]


def test_empty_golden_scores_zeros() -> None:
    report = run_golden((), _perfect_fn(()))
    assert isinstance(report, GoldenReport)
    assert report.n == 0
    assert report.entity_recall == 0.0
    assert report.answer_hit_rate == 0.0
    assert report.gap_precision == 0.0
    assert report.per_item == ()


def test_all_metrics_in_unit_interval() -> None:
    def answer_fn(question: str) -> Mapping[str, object]:
        # Deliberately imperfect: no entities, no substrings, spurious gaps.
        return {"entities": [], "answer": "", "gap": True}

    for golden in (_GOLDEN, ()):
        report = run_golden(golden, answer_fn)
        for value in (report.entity_recall, report.answer_hit_rate, report.gap_precision):
            assert 0.0 <= value <= 1.0


def test_as_dict_shape_and_values() -> None:
    report = run_golden(_GOLDEN, _perfect_fn(_GOLDEN))
    d = report.as_dict()
    assert set(d) == {"n", "entity_recall", "answer_hit_rate", "gap_precision", "per_item"}
    assert d["n"] == 3
    assert d["entity_recall"] == 1.0
    assert d["answer_hit_rate"] == 1.0
    assert d["gap_precision"] == 1.0
    assert isinstance(d["per_item"], list)
    assert len(d["per_item"]) == 3
    first = d["per_item"][0]
    assert set(first) == {
        "id",
        "entity_recall",
        "answer_hit",
        "predicted_gap",
        "expected_gap",
        "gap_match",
    }
    assert first["id"] == "q_ro"
    assert first["entity_recall"] == 1.0


def test_missing_result_keys_are_tolerated() -> None:
    # answer_fn may omit keys; defaults treat them as no entities / no gap.
    def answer_fn(question: str) -> Mapping[str, object]:
        return {}

    report = run_golden(_GOLDEN, answer_fn)
    assert report.entity_recall == 0.0
    # No substrings satisfied and no gaps predicted.
    assert report.answer_hit_rate == 0.0
    assert report.gap_precision == 0.0
    assert all(it.predicted_gap is False for it in report.per_item)
