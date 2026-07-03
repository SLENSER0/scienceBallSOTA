"""Tests for leave-one-out ablation contribution matrix (§23.31/§23.19).

Проверяются: знак и величина вклада (больше/меньше — лучше), нулевой вклад при
равенстве абляции полному счёту, ранжирование по убыванию, самый важный
компонент, пустой ввод и вредный компонент (абляция лучше полного).
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.ablation_contribution import (
    AblationReport,
    ComponentContribution,
    analyze,
)


def test_higher_is_better_contributions_and_ranking() -> None:
    """full 0.9 vs {reranker:0.7, proximity:0.85} → 0.2 / 0.05, top=reranker."""
    report = analyze(0.9, {"reranker": 0.7, "proximity": 0.85})
    by_name = {c.component: c for c in report.components}
    assert by_name["reranker"].contribution == pytest.approx(0.2)
    assert by_name["proximity"].contribution == pytest.approx(0.05)
    assert report.most_important == "reranker"
    assert report.higher_is_better is True
    assert report.full_score == pytest.approx(0.9)


def test_components_sorted_descending_by_contribution() -> None:
    """Кортеж компонентов отсортирован по вкладу по убыванию."""
    report = analyze(0.9, {"reranker": 0.7, "proximity": 0.85, "verifier": 0.6})
    contribs = [c.contribution for c in report.components]
    assert contribs == sorted(contribs, reverse=True)
    assert [c.component for c in report.components] == ["verifier", "reranker", "proximity"]


def test_zero_contribution_when_ablated_equals_full() -> None:
    """Компонент, чья абляция равна полному счёту, имеет вклад 0.0."""
    report = analyze(0.8, {"noop": 0.8})
    assert report.components[0].contribution == pytest.approx(0.0)
    assert report.most_important == "noop"


def test_lower_is_better_positive_contribution() -> None:
    """higher_is_better=False, full 0.2 latency, абляция 0.3 → вклад +0.1."""
    report = analyze(0.2, {"cache": 0.3}, higher_is_better=False)
    assert report.higher_is_better is False
    assert report.components[0].contribution == pytest.approx(0.1)
    assert report.most_important == "cache"


def test_empty_ablated_gives_none_most_important() -> None:
    """Пустой ``ablated`` → components пуст, most_important None."""
    report = analyze(0.5, {})
    assert report.components == ()
    assert report.most_important is None


def test_harmful_component_negative_contribution() -> None:
    """Абляция лучше полного (higher_is_better) → отрицательный вклад."""
    report = analyze(0.7, {"harmful": 0.85})
    assert report.components[0].contribution == pytest.approx(-0.15)
    assert report.components[0].contribution < 0.0


def test_harmful_ranks_below_helpful() -> None:
    """Полезный компонент стоит выше вредного в ранжировании."""
    report = analyze(0.7, {"harmful": 0.85, "helpful": 0.5})
    assert [c.component for c in report.components] == ["helpful", "harmful"]
    assert report.most_important == "helpful"


def test_as_dict_roundtrip() -> None:
    """``as_dict`` даёт JSON-совместимое представление обоих dataclass'ов."""
    report = analyze(0.9, {"reranker": 0.7})
    d = report.as_dict()
    assert d == {
        "full_score": 0.9,
        "higher_is_better": True,
        "components": [
            {"component": "reranker", "ablated_score": 0.7, "contribution": 0.2},
        ],
        "most_important": "reranker",
    }
    comp = report.components[0]
    assert comp.as_dict() == {
        "component": "reranker",
        "ablated_score": 0.7,
        "contribution": 0.2,
    }


def test_frozen_dataclasses() -> None:
    """Оба dataclass'а заморожены (immutable)."""
    report = analyze(0.9, {"reranker": 0.7})
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.full_score = 0.1  # type: ignore[misc]
    comp = report.components[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        comp.contribution = 0.0  # type: ignore[misc]
    assert isinstance(comp, ComponentContribution)
    assert isinstance(report, AblationReport)
