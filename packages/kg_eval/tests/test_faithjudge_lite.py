"""Тесты FaithJudge-lite эвристического scorer'а верности (§18) — RU/EN."""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval import faithjudge_lite
from kg_eval.faithjudge_lite import (
    FaithScore,
    faithfulness_score,
    salient_tokens,
    split_claims,
)


def test_fully_grounded_score_one() -> None:
    """(1) Все токены claim покрыты evidence → score 1.0, ничего не выпало."""
    res = faithfulness_score(
        "The alloy hardness is 120 HV.",
        ["The alloy hardness is 120 HV and it is ductile."],
    )
    assert isinstance(res, FaithScore)
    assert res.supported == 1
    assert res.unsupported == 0
    assert res.score == 1.0
    assert res.unsupported_claims == ()


def test_fabricated_number_lowers_and_lists() -> None:
    """(2) Выдуманное число понижает score и попадает в список неподтверждённых."""
    res = faithfulness_score(
        "Tensile strength is 450 MPa. Density is 999 g.",
        ["Tensile strength is 450 MPa; density is 8 g."],
    )
    assert res.supported == 1
    assert res.unsupported == 1
    assert res.score == 0.5
    assert len(res.unsupported_claims) == 1
    assert "999" in res.unsupported_claims[0]


def test_no_evidence_score_zero() -> None:
    """(3) Без evidence содержательный claim не может быть подтверждён → 0.0."""
    res = faithfulness_score("Tensile strength is 450 MPa.", [])
    assert res.supported == 0
    assert res.unsupported == 1
    assert res.score == 0.0
    assert res.unsupported_claims == ("Tensile strength is 450 MPa",)


def test_empty_answer_is_vacuously_faithful() -> None:
    """(4) Пустой ответ = нет claims → вакуумно верен, score 1.0."""
    res = faithfulness_score("   \n  ", ["irrelevant evidence 1 2 3"])
    assert res.supported == 0
    assert res.unsupported == 0
    assert res.score == 1.0
    assert res.unsupported_claims == ()


def test_partial_support() -> None:
    """(5) Частичное покрытие: 2 из 3 claims подтверждены → score 2/3."""
    res = faithfulness_score(
        "Hardness is 120 HV. Melting point is 1500 C. Color is blue.",
        ["Hardness is 120 HV.", "Melting point is 1500 C."],
    )
    assert res.supported == 2
    assert res.unsupported == 1
    assert res.score == pytest.approx(2 / 3)
    assert res.unsupported_claims == ("Color is blue",)


def test_numeric_claim_matched_and_mismatched() -> None:
    """(6) Совпавшее число → supported; несовпавшее → unsupported + list."""
    matched = faithfulness_score(
        "The yield is 42.5 percent.",
        ["Measured yield 42.5 percent in trials."],
    )
    assert matched.score == 1.0
    assert matched.unsupported_claims == ()

    mismatched = faithfulness_score(
        "The yield is 42.5 percent.",
        ["Measured yield 40.0 percent in trials."],
    )
    assert mismatched.score == 0.0
    assert mismatched.unsupported_claims == ("The yield is 42.5 percent",)


def test_as_dict_shape_and_rounding() -> None:
    """(7) as_dict → plain ints/float(list) с округлением score до 6 знаков."""
    res = faithfulness_score(
        "Hardness is 120 HV. Color is blue.",
        ["Hardness is 120 HV."],
    )
    d = res.as_dict()
    assert d == {
        "supported": 1,
        "unsupported": 1,
        "score": 0.5,
        "unsupported_claims": ["Color is blue"],
    }
    assert isinstance(d["unsupported_claims"], list)
    assert isinstance(d["score"], float)


def test_module_docstring_cites_paper() -> None:
    """(8) Docstring модуля цитирует источник (arXiv:2505.04847, FaithJudge)."""
    doc = faithjudge_lite.__doc__ or ""
    assert "2505.04847" in doc
    assert "FaithJudge" in doc
    # Отмечена open-weight подстановка вместо закрытого судьи (§23.33).
    assert "open-weight" in doc.lower()


def test_vacuous_claim_supported_without_evidence() -> None:
    """(9) Claim без значимых токенов (одни стоп-слова) вакуумно подтверждён."""
    res = faithfulness_score("It is.", [])
    assert res.supported == 1
    assert res.unsupported == 0
    assert res.score == 1.0


def test_frozen_dataclass_is_immutable() -> None:
    """(10) FaithScore заморожен — присваивание полю бросает FrozenInstanceError."""
    res = faithfulness_score("Hardness is 120 HV.", ["Hardness is 120 HV."])
    assert dataclasses.is_dataclass(res)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.score = 0.0  # type: ignore[misc]


def test_split_claims_and_salient_tokens() -> None:
    """(11) Утилиты: разбиение на предложения и извлечение значимых токенов."""
    assert split_claims("A is 1. B is 2; C is 3!") == ["A is 1", "B is 2", "C is 3"]
    numbers, words = salient_tokens("The hardness is 120 HV")
    assert numbers == frozenset({120.0})
    # Стоп-слова the/is отброшены; остаются содержательные слова.
    assert words == frozenset({"hardness", "hv"})
