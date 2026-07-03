"""§7.4 numeric value parser — hand-checked cases (RU & EN)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.value_parser import ParsedValue, parse_value


def test_bare_value_with_unit_148_hv() -> None:
    pv = parse_value("148 HV")
    assert pv is not None
    assert pv.operator == "eq"
    assert pv.value == 148.0
    assert pv.unit == "HV"
    assert pv.value_min is None and pv.value_max is None
    assert pv.uncertainty is None
    assert pv.source == "148 HV"


def test_lte_inequality_1000() -> None:
    pv = parse_value("≤ 1000 мг/дм³")
    assert pv is not None
    assert pv.operator == "lte"
    assert pv.value == 1000.0
    assert pv.unit == "мг/дм3"  # NFKC folds the ³ superscript to a plain 3


def test_lte_compact_no_unit() -> None:
    pv = parse_value("≤1000")
    assert pv is not None
    assert pv.operator == "lte" and pv.value == 1000.0
    assert pv.unit is None


def test_range_200_300_mpa() -> None:
    pv = parse_value("200–300 МПа")
    assert pv is not None
    assert pv.operator == "range"
    assert pv.value_min == 200.0 and pv.value_max == 300.0
    assert pv.value is None
    assert pv.unit == "МПа"


def test_approx_5_0() -> None:
    pv = parse_value("≈5.0")
    assert pv is not None
    assert pv.operator == "approx"
    assert pv.value == 5.0
    assert pv.unit is None


def test_uncertainty_5_0_pm_0_2() -> None:
    pv = parse_value("5.0 ± 0.2 %")
    assert pv is not None
    assert pv.operator == "eq"
    assert pv.value == 5.0
    assert pv.uncertainty == 0.2
    assert pv.unit == "%"


def test_scientific_e_notation_1e3() -> None:
    pv = parse_value("1e3")
    assert pv is not None
    assert pv.operator == "eq"
    assert pv.value == 1000.0
    assert pv.unit is None


def test_scientific_caret_notation_10_pow_3() -> None:
    pv = parse_value("10^3 А/м²")
    assert pv is not None
    assert pv.value == 1000.0
    assert pv.unit == "А/м2"  # NFKC folds the ² superscript to a plain 2


def test_decimal_comma_2_5() -> None:
    pv = parse_value("2,5")
    assert pv is not None
    assert pv.operator == "eq"
    assert pv.value == 2.5
    assert pv.unit is None


def test_bare_number_42() -> None:
    pv = parse_value("42")
    assert pv is not None
    assert pv.operator == "eq"
    assert pv.value == 42.0
    assert pv.unit is None
    assert pv.value_min is None and pv.value_max is None


def test_gte_and_gt_and_lt_symbols() -> None:
    assert parse_value("≥ 90 %").operator == "gte"  # type: ignore[union-attr]
    assert parse_value("> 5").operator == "gt"  # type: ignore[union-attr]
    assert parse_value("< 5").operator == "lt"  # type: ignore[union-attr]


def test_ru_word_operator_ne_bolee() -> None:
    pv = parse_value("не более 90 %")
    assert pv is not None
    assert pv.operator == "lte" and pv.value == 90.0
    assert pv.unit == "%"


def test_junk_returns_none() -> None:
    assert parse_value("нет данных") is None
    assert parse_value("abc") is None
    assert parse_value("") is None
    assert parse_value("   ") is None
    assert parse_value("-") is None


def test_as_dict_drops_none_fields() -> None:
    d = parse_value("148 HV").as_dict()  # type: ignore[union-attr]
    assert d == {"operator": "eq", "value": 148.0, "unit": "HV", "source": "148 HV"}

    rng = parse_value("200–300 МПа").as_dict()  # type: ignore[union-attr]
    assert rng == {
        "operator": "range",
        "value_min": 200.0,
        "value_max": 300.0,
        "unit": "МПа",
        "source": "200–300 МПа",
    }


def test_frozen_dataclass_is_immutable() -> None:
    pv = ParsedValue(value=1.0, operator="eq", source="1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        pv.value = 2.0  # type: ignore[misc]
