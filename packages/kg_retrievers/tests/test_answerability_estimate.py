"""§25.15 tests — retriever-side answerability estimate over coverage cells.

Hand-checkable: каждая проверка задаёт явные ячейки и сверяет долю присутствия,
минимальную уверенность отсутствия и итоговое решение.
"""

from __future__ import annotations

from kg_retrievers.answerability_estimate import (
    AnswerabilityEstimate,
    estimate_answerability,
)


def _covered() -> dict:
    return {"status": "COVERED"}


def _absent(confidence: float) -> dict:
    return {"status": "ABSENT", "confidence_of_absence": confidence}


def test_all_covered_answers_full_fraction() -> None:
    """(1) все COVERED -> present_fraction==1.0, decision=='answer', ndc==1.0."""
    est = estimate_answerability([_covered(), _covered(), _covered()])
    assert est.n_cells == 3
    assert est.n_present == 3
    assert est.present_fraction == 1.0
    assert est.no_data_confidence == 1.0
    assert est.decision == "answer"


def test_one_of_two_present_answers_at_half() -> None:
    """(2) 1 из 2 присутствует -> present_fraction==0.5, decision=='answer'."""
    est = estimate_answerability([_covered(), _absent(0.9)])
    assert est.present_fraction == 0.5
    assert est.decision == "answer"


def test_zero_present_high_absence_confidence_reports_absence() -> None:
    """(3) 0 присутствует, уверенность отсутствия 0.9 -> 'report_absence'."""
    est = estimate_answerability([_absent(0.9), _absent(0.95)])
    assert est.n_present == 0
    assert est.present_fraction == 0.0
    assert est.no_data_confidence == 0.9
    assert est.decision == "report_absence"


def test_zero_present_low_absence_confidence_abstains() -> None:
    """(4) 0 присутствует, уверенность отсутствия 0.2 -> 'abstain'."""
    est = estimate_answerability([_absent(0.2)])
    assert est.no_data_confidence == 0.2
    assert est.decision == "abstain"


def test_no_data_confidence_is_min_over_absent_cells() -> None:
    """(5) no_data_confidence == минимум по нескольким отсутствующим ячейкам."""
    est = estimate_answerability([_absent(0.8), _absent(0.4), _absent(0.6)])
    assert est.no_data_confidence == 0.4
    # min 0.4 >= abstain_below default 0.3 -> уверенный пробел
    assert est.decision == "report_absence"


def test_empty_cells_abstains() -> None:
    """(6) пустой вход -> n_cells==0, present_fraction==0.0, decision=='abstain'."""
    est = estimate_answerability([])
    assert est.n_cells == 0
    assert est.present_fraction == 0.0
    assert est.no_data_confidence == 1.0
    assert est.decision == "abstain"


def test_present_cell_ignores_absence_confidence() -> None:
    """COVERED-ячейка считается присутствующей независимо от прочих полей."""
    est = estimate_answerability([{"status": "covered"}])  # case-insensitive
    assert est.n_present == 1
    assert est.decision == "answer"


def test_custom_thresholds_shift_decision() -> None:
    """Пороги настраиваемы: поднятый answer_at убирает 'answer' на доле 0.5."""
    cells = [_covered(), _absent(0.1)]
    est = estimate_answerability(cells, answer_at=0.75, abstain_below=0.3)
    assert est.present_fraction == 0.5
    # 0.5 < 0.75 -> не answer; ndc 0.1 < 0.3 -> abstain
    assert est.decision == "abstain"


def test_as_dict_roundtrip() -> None:
    """as_dict() возвращает все поля оценки / exposes every field."""
    est = estimate_answerability([_covered(), _absent(0.5)])
    assert est.as_dict() == {
        "n_cells": 2,
        "n_present": 1,
        "present_fraction": 0.5,
        "no_data_confidence": 0.5,
        "decision": "answer",
    }
    assert isinstance(est, AnswerabilityEstimate)
