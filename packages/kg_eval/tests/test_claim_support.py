"""Тесты детерминированной разметки claim-support (§18.8/§18.10) — RU/EN."""

from __future__ import annotations

from kg_eval.claim_support import Claim, ClaimSupportResult, label_claims, split_claims


def test_supported_number_present() -> None:
    """(1) Число из claim есть в процитированном evidence → supported, rate 0.0."""
    res = label_claims("Hardness is 120 HV [e1].", {"e1": "measured 120 HV"})
    assert isinstance(res, ClaimSupportResult)
    assert len(res.claims) == 1
    claim = res.claims[0]
    assert isinstance(claim, Claim)
    assert claim.cited_ids == ("e1",)
    assert claim.numbers == (120.0,)
    assert claim.supported is True
    assert res.unsupported_claim_rate == 0.0
    assert res.citation_precision == 1.0


def test_number_mismatch_unsupported() -> None:
    """(2) Число не совпадает с evidence → not supported, rate 1.0."""
    res = label_claims("Hardness is 120 HV [e1].", {"e1": "measured 150 HV"})
    assert res.claims[0].supported is False
    assert res.unsupported_claim_rate == 1.0
    # Цитата существует, поэтому precision остаётся 1.0.
    assert res.citation_precision == 1.0


def test_no_citation_unsupported() -> None:
    """(3) Claim без цитаты не может быть подтверждён."""
    res = label_claims("Hardness is 120 HV.", {"e1": "measured 120 HV"})
    claim = res.claims[0]
    assert claim.cited_ids == ()
    assert claim.supported is False
    assert res.unsupported_claim_rate == 1.0
    # Ни одной цитаты → precision 0.0 (защита от деления на ноль).
    assert res.citation_precision == 0.0


def test_phantom_citation() -> None:
    """(4) Фантомный id [e9] отсутствует в evidence → not supported, precision 0.0."""
    res = label_claims("Hardness is 120 HV [e9].", {"e1": "measured 120 HV"})
    assert res.claims[0].cited_ids == ("e9",)
    assert res.claims[0].supported is False
    assert res.citation_precision == 0.0


def test_two_claims_half_rate() -> None:
    """(5) Два предложения: одно supported, одно нет → rate 0.5."""
    answer = "Hardness is 120 HV [e1]. Density is 8 g [e9]."
    res = label_claims(answer, {"e1": "measured 120 HV"})
    assert len(res.claims) == 2
    assert res.claims[0].supported is True
    assert res.claims[1].supported is False
    assert res.unsupported_claim_rate == 0.5
    # Одна из двух цитат существует.
    assert res.citation_precision == 0.5


def test_empty_answer() -> None:
    """(6) Пустой ответ → 0 claims, rate 0.0, precision 0.0."""
    res = label_claims("   ", {"e1": "measured 120 HV"})
    assert res.claims == ()
    assert res.unsupported_claim_rate == 0.0
    assert res.citation_precision == 0.0


def test_as_dict_rounded_float() -> None:
    """(7) as_dict()['unsupported_claim_rate'] — округлённый float."""
    answer = "A is 1 [e1]. B is 2 [e1]. C is 3 [e2]."
    res = label_claims(answer, {"e1": "1 and 2", "e2": "999"})
    d = res.as_dict()
    rate = d["unsupported_claim_rate"]
    assert isinstance(rate, float)
    # Один из трёх claims не подтверждён → 1/3.
    assert rate == round(1 / 3, 6)
    assert isinstance(d["citation_precision"], float)


def test_split_claims_boundaries() -> None:
    """split_claims режет по ./;/newline и отбрасывает пустые фрагменты."""
    assert split_claims("a. b; c\nd") == ["a", "b", "c", "d"]
    assert split_claims("") == []
    assert split_claims("  ; . \n") == []


def test_citation_digits_not_counted_as_numbers() -> None:
    """Цифры внутри маркера [e1] не должны попадать в извлечённые числа."""
    res = label_claims("Value is 120 HV [e1].", {"e1": "120 HV"})
    assert res.claims[0].numbers == (120.0,)
    assert res.claims[0].supported is True
