"""Multi-parameter numeric constraint parsing (§24.4)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.constraints import parse_constraints


def test_leq_1000_mg_dm3() -> None:
    cs = parse_constraints("≤1000 мг/дм³")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == "<=" and c.value == 1000.0
    assert c.parameter is None
    assert c.normalized_unit == "mg/L" and c.normalized_value == 1000.0


def test_range_200_300_with_parameter() -> None:
    cs = parse_constraints("сульфаты 200–300 мг/л")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == "range"
    assert c.min == 200.0 and c.max == 300.0
    assert c.parameter == "сульфаты" and c.unit == "мг/л"
    assert c.normalized_unit == "mg/L"
    assert c.normalized_min == 200.0 and c.normalized_max == 300.0


def test_ne_menee_90_percent() -> None:
    cs = parse_constraints("не менее 90%")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == ">=" and c.value == 90.0
    assert c.parameter is None and c.unit == "%"


def test_bare_current_density_with_parameter() -> None:
    cs = parse_constraints("плотность тока 250 А/м²")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == "=" and c.value == 250.0
    assert c.parameter == "плотность тока"
    assert c.normalized_unit == "A/m^2" and c.normalized_value == 250.0


def test_bare_percent_with_parameter() -> None:
    cs = parse_constraints("извлечение 95%")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == "=" and c.value == 95.0
    assert c.unit == "%" and c.parameter == "извлечение"


def test_decimal_comma() -> None:
    cs = parse_constraints("плотность 1,5 г/л")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == "=" and c.value == 1.5
    assert c.unit == "г/л" and c.parameter == "плотность"


def test_multiple_constraints_one_string() -> None:
    cs = parse_constraints("сульфаты 200–300 мг/л, плотность тока 250 А/м²")
    assert len(cs) == 2
    assert [c.operator for c in cs] == ["range", "="]
    assert cs[0].parameter == "сульфаты" and cs[0].min == 200.0 and cs[0].max == 300.0
    assert cs[1].parameter == "плотность тока" and cs[1].value == 250.0


def test_ne_bolee_inequality_english_unit() -> None:
    cs = parse_constraints("не более 1000 mg/L")
    assert len(cs) == 1
    c = cs[0]
    assert c.operator == "<=" and c.value == 1000.0 and c.normalized_unit == "mg/L"


def test_no_constraint_text_returns_empty() -> None:
    assert parse_constraints("Общие сведения о процессе флотации меди") == []
    assert parse_constraints("") == []


def test_as_dict_shape() -> None:
    c = parse_constraints("сульфаты 200–300 мг/л")[0]
    d = c.as_dict()
    assert d["parameter"] == "сульфаты"
    assert d["operator"] == "range"
    assert d["min"] == 200.0 and d["max"] == 300.0
    assert "value" not in d  # unset numeric fields are dropped
    assert d["source_span"] == "200–300 мг/л"


def test_constraint_is_frozen() -> None:
    c = parse_constraints("не менее 90%")[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.value = 5.0


def test_source_span_recorded() -> None:
    c = parse_constraints("плотность тока 250 А/м²")[0]
    assert "250" in c.source_span
