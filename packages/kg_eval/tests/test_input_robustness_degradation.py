"""Tests for input-robustness degradation scoring (§23.17).

Ручные проверки на маленьких, вычислимых от руки входах.
Hand-checkable assertions on small, hand-verifiable inputs.
"""

from __future__ import annotations

import pytest

from kg_eval.input_robustness_degradation import (
    PerturbationDrop,
    RobustnessReport,
    score_robustness,
)


def test_no_drop_everywhere_is_perfectly_robust() -> None:
    """perturbed == clean на каждой строке -> robustness 1.0, passed, worst=первое имя."""
    rows = [
        {"name": "ocr", "clean": 0.8, "perturbed": 0.8},
        {"name": "encoding", "clean": 0.6, "perturbed": 0.6},
    ]
    rep = score_robustness(rows)
    assert rep.robustness == 1.0
    assert rep.passed is True
    # Все rel_drop равны 0.0 -> ничья по алфавиту: 'encoding' < 'ocr'.
    assert rep.worst == "encoding"


def test_single_row_half_drop_fails() -> None:
    """clean=1.0 perturbed=0.5 -> abs_drop 0.5, rel_drop 0.5, passed False."""
    rep = score_robustness([{"name": "ocr", "clean": 1.0, "perturbed": 0.5}])
    assert rep.n == 1
    assert rep.mean_clean == 1.0
    assert rep.mean_perturbed == 0.5
    assert rep.robustness == 0.5
    assert rep.worst == "ocr"
    assert rep.passed is False


def test_two_rows_means_and_worst() -> None:
    """Средние по двум строкам считаются верно; worst = большая rel_drop."""
    rows = [
        {"name": "light", "clean": 1.0, "perturbed": 0.9},  # rel_drop 0.1
        {"name": "heavy", "clean": 1.0, "perturbed": 0.4},  # rel_drop 0.6
    ]
    rep = score_robustness(rows)
    assert rep.n == 2
    assert rep.mean_clean == pytest.approx(1.0)
    assert rep.mean_perturbed == pytest.approx(0.65)
    assert rep.robustness == pytest.approx(0.65)
    assert rep.worst == "heavy"
    assert rep.passed is False


def test_clean_zero_row_no_div_by_zero() -> None:
    """clean=0.0 -> rel_drop 0.0, деления на ноль нет."""
    rep = score_robustness([{"name": "empty", "clean": 0.0, "perturbed": 0.0}])
    assert rep.robustness == 1.0  # mean_clean == 0 -> 1.0
    assert rep.worst == "empty"
    assert rep.passed is True


def test_clean_zero_row_relative_drop_is_zero_field() -> None:
    """Поле rel_drop у строки clean=0 равно 0.0 (проверяем через score_robustness)."""
    rep = score_robustness(
        [
            {"name": "zero", "clean": 0.0, "perturbed": 0.5},
            {"name": "keep", "clean": 1.0, "perturbed": 1.0},
        ]
    )
    # zero-строка не должна становиться worst из-за rel_drop==0.0.
    assert rep.worst == "keep"
    assert rep.passed is True


def test_threshold_flips_pass() -> None:
    """max_rel_drop=0.6 переводит 0.5-просадку в passed True."""
    rows = [{"name": "ocr", "clean": 1.0, "perturbed": 0.5}]
    assert score_robustness(rows, max_rel_drop=0.6).passed is True
    assert score_robustness(rows, max_rel_drop=0.2).passed is False


def test_improvement_gives_negative_drops_and_robustness_above_one() -> None:
    """perturbed > clean -> abs/rel_drop отрицательны, robustness > 1.0."""
    rows = [{"name": "boost", "clean": 0.5, "perturbed": 0.75}]
    rep = score_robustness(rows)
    assert rep.robustness == pytest.approx(1.5)
    assert rep.robustness > 1.0
    assert rep.passed is True  # rel_drop=-0.5 <= 0.2


def test_perturbation_drop_fields_and_as_dict() -> None:
    """PerturbationDrop.as_dict возвращает все поля."""
    d = PerturbationDrop(name="ocr", clean=1.0, perturbed=0.5, abs_drop=0.5, rel_drop=0.5)
    assert d.as_dict() == {
        "name": "ocr",
        "clean": 1.0,
        "perturbed": 0.5,
        "abs_drop": 0.5,
        "rel_drop": 0.5,
    }


def test_report_as_dict_roundtrip() -> None:
    """RobustnessReport.as_dict содержит все агрегаты."""
    rep = score_robustness([{"name": "ocr", "clean": 1.0, "perturbed": 0.5}])
    assert rep.as_dict() == {
        "n": 1,
        "mean_clean": 1.0,
        "mean_perturbed": 0.5,
        "robustness": 0.5,
        "worst": "ocr",
        "passed": False,
    }
    assert isinstance(rep, RobustnessReport)


def test_worst_ties_broken_alphabetically() -> None:
    """Равные rel_drop -> worst выбирается по алфавиту."""
    rows = [
        {"name": "zeta", "clean": 1.0, "perturbed": 0.5},
        {"name": "alpha", "clean": 1.0, "perturbed": 0.5},
    ]
    assert score_robustness(rows).worst == "alpha"


def test_empty_raises_value_error() -> None:
    """Пустой вход -> ValueError."""
    with pytest.raises(ValueError):
        score_robustness([])
