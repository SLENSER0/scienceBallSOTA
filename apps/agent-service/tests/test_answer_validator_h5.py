"""H-5 regression: only *measurable* numbers require a citation.

The old validator flagged ANY bare digit — years, ordinal counts, table labels —
as an uncited numeric claim, which forced the verifier to mark the answer
«unverified» and cut its confidence. These cases assert that incidental numbers
are now ignored while genuine measured quantities (число+единица, or a number in
a sentence about a measured property) are still flagged when uncited.
"""

from __future__ import annotations

from agent_service.answer_validator import validate_answer

_CITED: list[dict[str, int]] = [{"n": 1}]


# --- incidental numbers must NOT be flagged (no citation required) ----------
def test_years_are_not_numeric_claims() -> None:
    res = validate_answer("Метод предложен в 1998 году и обновлён в 2015.", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []


def test_ordinal_counts_are_not_numeric_claims() -> None:
    res = validate_answer("Процесс состоит из 5 стадий и 3 этапов.", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []


def test_table_and_figure_labels_are_not_claims() -> None:
    res = validate_answer("Смотри таблицу 2 и рисунок 3 ниже.", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []


def test_standard_number_is_not_a_claim() -> None:
    res = validate_answer("Реагент подаётся согласно ГОСТ 12345.", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []


# --- measurable numbers WITHOUT a marker are still flagged ------------------
def test_unit_bearing_number_is_flagged() -> None:
    res = validate_answer("Концентрация сульфатов 200 мг/л в стоке.", _CITED)
    assert res.numeric_claims_without_evidence == ["200"]


def test_percentage_is_flagged() -> None:
    res = validate_answer("Эффективность достигает 87%.", _CITED)
    assert res.numeric_claims_without_evidence == ["87%"]


def test_property_context_number_is_flagged() -> None:
    res = validate_answer("Твёрдость равна 9 по шкале Мооса.", _CITED)
    assert res.numeric_claims_without_evidence == ["9"]


# --- mixed: incidental excluded, measurable kept, in one sentence -----------
def test_year_excluded_measured_value_kept() -> None:
    res = validate_answer("В 2015 году твёрдость составила 148 HV.", _CITED)
    # the year 2015 is incidental; only the measured 148 HV needs evidence.
    assert res.numeric_claims_without_evidence == ["148"]


def test_ordinal_excluded_unit_value_kept() -> None:
    res = validate_answer("КПД растёт за 3 этапа до 95%.", _CITED)
    assert res.numeric_claims_without_evidence == ["95%"]


def test_measurable_number_with_marker_is_grounded() -> None:
    # a unit-bearing number in a [1]-cited sentence stays grounded (unchanged).
    res = validate_answer("Скорость потока 1.2 см/с подтверждена [1].", _CITED)
    assert res.ok is True
    assert res.numeric_claims_without_evidence == []
