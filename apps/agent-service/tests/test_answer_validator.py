"""Hand-checked tests for §13.12 answer validation.

Pure-python, no store / no LLM: feed rendered answer text plus a citations list
and assert exactly which numbers are flagged as unsupported. Every expected value
is spelled out so the test is verifiable by hand. The grounding rule is
sentence-scoped: a number is grounded iff its sentence carries an inline ``[n]``
marker and the citations list is non-empty.
"""

from __future__ import annotations

import pytest
from agent_service.answer_validator import AnswerValidation, validate_answer

# A non-empty citations list — the validator only checks ``len(...) > 0``.
_CITED: list[dict[str, int]] = [{"n": 1}]


# ---------------------------------------------------------------------------
# grounded numbers: marker in the sentence + citations attached
# ---------------------------------------------------------------------------
def test_numeric_claim_with_marker_is_ok() -> None:
    # "1.2" sits in a sentence carrying [1] and citations are attached → grounded.
    res = validate_answer("Католит подаётся со скоростью 1.2 см/с [1].", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []
    assert res.has_citations is True
    assert res.issues == []


def test_several_numbers_share_one_marker_in_sentence() -> None:
    # Both numbers live in the same [1]-cited sentence → both grounded.
    res = validate_answer("Скорость 1.2 см/с и температура 25 °C подтверждены [1].", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []


# ---------------------------------------------------------------------------
# ungrounded numbers: number present, no marker in its sentence
# ---------------------------------------------------------------------------
def test_numeric_claim_without_marker_is_flagged() -> None:
    # Citations exist, but the sentence with "9" has no [n] marker → flagged.
    res = validate_answer("Твёрдость минерала равна 9 по шкале Мооса.", _CITED)
    assert res.ok is False
    assert res.numeric_claims_without_evidence == ["9"]
    assert res.has_citations is True
    assert len(res.issues) == 1
    assert "9" in res.issues[0]


def test_hardness_value_is_flagged() -> None:
    # A decimal hardness reading with no marker → flagged verbatim, comma decimal kept.
    res = validate_answer("Твёрдость по шкале Мооса равна 9,5.", _CITED)
    assert res.ok is False
    assert res.numeric_claims_without_evidence == ["9,5"]


def test_percentages_are_counted_as_numbers() -> None:
    # A trailing-% token is a numeric claim; no marker here → flagged as "87%".
    res = validate_answer("КПД процесса составляет 87%.", _CITED)
    assert res.ok is False
    assert res.numeric_claims_without_evidence == ["87%"]


# ---------------------------------------------------------------------------
# no numbers / no citations
# ---------------------------------------------------------------------------
def test_answer_with_no_numbers_is_ok() -> None:
    # No numeric claims at all → ok even without any citations attached.
    res = validate_answer("Электролиз идёт в щелочной среде без числовых значений.", [])
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []
    assert res.has_citations is False
    assert res.issues == []


def test_no_citations_flags_every_number() -> None:
    # An inline [1] is present but the citations list is empty → nothing to ground
    # on, so "95%" is flagged and a global no-citations issue is raised.
    res = validate_answer("Выход по току достигает 95% при оптимуме [1].", [])
    assert res.ok is False
    assert res.numeric_claims_without_evidence == ["95%"]
    assert res.has_citations is False
    assert res.issues[0] == "ответ без цитат / answer has no citations"
    assert len(res.issues) == 2  # global note + one per-number note


# ---------------------------------------------------------------------------
# mixed: one grounded sentence, one ungrounded
# ---------------------------------------------------------------------------
def test_mixed_grounded_and_ungrounded() -> None:
    answer = "Скорость потока составляет 1.2 см/с [1]. Твёрдость образца равна 9 по Моосу."
    res = validate_answer(answer, _CITED)
    assert res.ok is False
    # "1.2" is grounded (its sentence has [1]); only "9" is left unsupported.
    assert res.numeric_claims_without_evidence == ["9"]
    assert res.has_citations is True


def test_citation_marker_digits_are_not_claims() -> None:
    # The "1" inside [1] must not be mistaken for a numeric claim.
    res = validate_answer("Согласно источнику [1], реакция протекает полностью.", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []


# ---------------------------------------------------------------------------
# as_dict + immutability
# ---------------------------------------------------------------------------
def test_as_dict_exact_shape() -> None:
    res = validate_answer("Твёрдость равна 9.", _CITED)
    assert res.as_dict() == {
        "ok": False,
        "numeric_claims_without_evidence": ["9"],
        "has_citations": True,
        "issues": ["числовое утверждение «9» без ссылки / numeric claim «9» without citation"],
    }


def test_result_is_frozen() -> None:
    res = validate_answer("Без чисел.", _CITED)
    assert isinstance(res, AnswerValidation)
    with pytest.raises(AttributeError):
        res.ok = True  # type: ignore[misc]  # frozen dataclass — immutable
