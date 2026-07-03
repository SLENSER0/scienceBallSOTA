"""§6.20 numeric literal normalization — hand-checked cases (RU & EN)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.numeric_normalize import (
    NumberParse,
    describe_number,
    normalize_number,
    parse_percent,
)


def test_decimal_comma_2_5() -> None:
    assert normalize_number("2,5") == 2.5


def test_scientific_e_notation_1e3() -> None:
    assert normalize_number("1e3") == 1000.0


def test_scientific_caret_10_pow_3() -> None:
    assert normalize_number("10^3") == 1000.0


def test_scientific_caret_negative_exponent() -> None:
    assert normalize_number("10^-3") == pytest.approx(0.001)


def test_space_thousands_1_000() -> None:
    assert normalize_number("1 000") == 1000.0


def test_nbsp_and_narrow_nbsp_thousands() -> None:
    # U+00A0 no-break space and U+202F narrow no-break space as group separators.
    assert normalize_number("12 345") == 12345.0
    assert normalize_number("12 345") == 12345.0


def test_comma_grouped_thousands() -> None:
    assert normalize_number("1,000") == 1000.0
    assert normalize_number("1,000,000") == 1000000.0


def test_mixed_grouping_and_decimal_last_separator_wins() -> None:
    # US shape: comma groups, period decimal. EU shape: period groups, comma decimal.
    assert normalize_number("1,000.5") == 1000.5
    assert normalize_number("1.000,5") == 1000.5


def test_unicode_vulgar_fractions_plain_and_mixed() -> None:
    assert normalize_number("½") == 0.5
    assert normalize_number("2½") == 2.5
    assert normalize_number("2 ½") == 2.5


def test_range_midpoint_10_20() -> None:
    assert normalize_number("10-20") == 15.0


def test_range_midpoint_en_dash_and_ru_words() -> None:
    assert normalize_number("200–300") == 250.0
    assert normalize_number("от 100 до 300") == 200.0


def test_negative_ascii_and_unicode_minus() -> None:
    assert normalize_number("-5") == -5.0
    assert normalize_number("−5") == -5.0  # U+2212 unicode minus


def test_parse_percent_50() -> None:
    assert parse_percent("50%") == 0.5


def test_parse_percent_decimal_comma_and_bare() -> None:
    assert parse_percent("2,5 %") == pytest.approx(0.025)
    assert parse_percent("50") == 0.5


def test_junk_returns_none() -> None:
    assert normalize_number("нет данных") is None
    assert normalize_number("abc") is None
    assert normalize_number("") is None
    assert normalize_number("   ") is None
    assert normalize_number("-") is None
    assert parse_percent("abc") is None
    assert parse_percent("%") is None


def test_describe_number_reports_kind() -> None:
    assert describe_number("2,5").as_dict() == {  # type: ignore[union-attr]
        "value": 2.5,
        "kind": "decimal_comma",
        "source": "2,5",
    }
    assert describe_number("10-20").kind == "range"  # type: ignore[union-attr]
    assert describe_number("1 000").kind == "thousands"  # type: ignore[union-attr]
    assert describe_number("1e3").kind == "scientific"  # type: ignore[union-attr]
    assert describe_number("½").kind == "fraction"  # type: ignore[union-attr]
    assert describe_number("нет данных") is None


def test_number_parse_frozen_dataclass_is_immutable() -> None:
    parsed = NumberParse(value=1.0, kind="plain", source="1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        parsed.value = 2.0  # type: ignore[misc]
