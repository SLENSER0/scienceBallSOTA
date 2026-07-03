"""Тесты NLI-агрегатора верности (§23.31/§23.35) — RU/EN, ручная проверка."""

from __future__ import annotations

import math

import pytest

from kg_eval.faithfulness_nli_score import FaithfulnessReport, score_faithfulness


def _v(label: str, weight: float = 1.0) -> dict[str, object]:
    """Хелпер: один NLI-вердикт / one NLI verdict."""
    return {"label": label, "weight": weight}


def test_all_entail_is_fully_faithful() -> None:
    """Все ``entail`` → faithfulness 1.0, без галлюцинаций, faithful True."""
    report = score_faithfulness([_v("entail"), _v("entail"), _v("entail")])
    assert report.faithfulness == 1.0
    assert report.hallucination_rate == 0.0
    assert report.contradiction_rate == 0.0
    assert report.faithful is True
    assert report.n == 3
    assert report.n_entail == 3


def test_all_contradict_is_fully_unfaithful() -> None:
    """Все ``contradict`` → faithfulness 0.0, contradiction 1.0, faithful False."""
    report = score_faithfulness([_v("contradict"), _v("contradict")])
    assert report.faithfulness == 0.0
    assert report.contradiction_rate == 1.0
    assert report.hallucination_rate == 1.0
    assert report.faithful is False
    assert report.n_contradict == 2


def test_mixed_unit_weights() -> None:
    """[entail,entail,neutral,contradict] → 0.5 / 0.5 / 0.25 (ручной счёт)."""
    report = score_faithfulness([_v("entail"), _v("entail"), _v("neutral"), _v("contradict")])
    assert report.faithfulness == 0.5
    assert report.hallucination_rate == 0.5
    assert report.contradiction_rate == 0.25
    assert report.faithful is False
    assert (report.n_entail, report.n_neutral, report.n_contradict) == (2, 1, 1)


def test_single_contradiction_gates_faithful() -> None:
    """Один contradict среди многих entail → faithful False (гейт)."""
    # 19 entail + 1 contradict → faithfulness 0.95 >= 0.9, но противоречие гейтит.
    verdicts = [_v("entail") for _ in range(19)] + [_v("contradict")]
    report = score_faithfulness(verdicts)
    assert report.faithfulness == 0.95
    assert report.faithfulness >= 0.9
    assert report.contradiction_rate == 0.05
    assert report.faithful is False


def test_weight_doubles_contradict_share() -> None:
    """weight=2.0 на contradict удваивает его долю vs unit-weight entail.

    2 entail (вес 1) + 1 contradict (вес 2): total=4, contradiction=2/4=0.5.
    Без веса было бы 1/3; вес 2.0 поднимает долю до 0.5.
    """
    report = score_faithfulness([_v("entail"), _v("entail"), _v("contradict", 2.0)])
    assert report.contradiction_rate == 0.5
    assert report.faithfulness == 0.5
    assert report.faithful is False


def test_bogus_label_raises() -> None:
    """Неизвестная метка → ValueError."""
    with pytest.raises(ValueError, match="unknown NLI label"):
        score_faithfulness([_v("entail"), _v("bogus")])


def test_empty_input_raises() -> None:
    """Пустой вход → ValueError."""
    with pytest.raises(ValueError, match="non-empty"):
        score_faithfulness([])


def test_as_dict_round_trips_and_rounds() -> None:
    """as_dict() возвращает ключи и округляет 1/3 до 0.333333."""
    report = score_faithfulness([_v("entail"), _v("neutral"), _v("contradict")])
    assert math.isclose(report.faithfulness, 1.0 / 3.0)
    data = report.as_dict()
    assert set(data) == {
        "n",
        "n_entail",
        "n_neutral",
        "n_contradict",
        "faithfulness",
        "hallucination_rate",
        "contradiction_rate",
        "faithful",
    }
    assert data["faithfulness"] == 0.333333
    assert data["hallucination_rate"] == 0.666667
    assert data["contradiction_rate"] == 0.333333
    assert data["n"] == 3
    assert data["faithful"] is False


def test_threshold_boundary_faithful() -> None:
    """Ровно порог без противоречий → faithful True."""
    # 9 entail + 1 neutral → faithfulness 0.9 == threshold, contradiction 0.
    verdicts = [_v("entail") for _ in range(9)] + [_v("neutral")]
    report = score_faithfulness(verdicts, threshold=0.9)
    assert report.faithfulness == 0.9
    assert report.contradiction_rate == 0.0
    assert report.faithful is True


def test_report_is_frozen() -> None:
    """FaithfulnessReport заморожен / frozen dataclass."""
    report = score_faithfulness([_v("entail")])
    assert isinstance(report, FaithfulnessReport)
    with pytest.raises((AttributeError, TypeError)):
        report.faithfulness = 0.0  # type: ignore[misc]
