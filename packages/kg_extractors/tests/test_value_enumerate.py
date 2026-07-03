"""§6.3 rule extractor — enumerate list/range values, hand-checked cases (RU & EN)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.value_enumerate import EnumeratedValue, enumerate_values


def test_comma_list_three_values_celsius() -> None:
    evs = enumerate_values("180, 200, 220 °C")
    assert [e.value for e in evs] == [180.0, 200.0, 220.0]
    assert all(e.kind == "list" for e in evs)


def test_comma_list_middle_value_span() -> None:
    text = "180, 200, 220 °C"
    evs = enumerate_values(text)
    middle = evs[1]
    assert text[middle.char_start : middle.char_end] == "200"
    assert middle.value == 200.0


def test_range_endpoints_2_4_hours() -> None:
    evs = enumerate_values("2-4 h")
    assert [e.value for e in evs] == [2.0, 4.0]
    assert all(e.kind == "range_endpoint" for e in evs)


def test_single_value_150_hv() -> None:
    evs = enumerate_values("150 HV")
    assert len(evs) == 1
    assert evs[0].kind == "single"
    assert evs[0].value == 150.0


def test_empty_text_returns_empty() -> None:
    assert enumerate_values("") == []
    assert enumerate_values("   ") == []


def test_no_numbers_returns_empty() -> None:
    assert enumerate_values("нет данных") == []
    assert enumerate_values("annealed") == []


def test_decimal_list_wt_percent() -> None:
    evs = enumerate_values("1.5, 2.5 wt%")
    assert [e.value for e in evs] == [1.5, 2.5]
    assert all(e.kind == "list" for e in evs)


def test_single_value_span_exact_digits() -> None:
    text = "150 HV"
    evs = enumerate_values(text)
    assert text[evs[0].char_start : evs[0].char_end] == "150"


def test_range_spans_exact_digits() -> None:
    text = "2-4 h"
    evs = enumerate_values(text)
    assert text[evs[0].char_start : evs[0].char_end] == "2"
    assert text[evs[1].char_start : evs[1].char_end] == "4"


def test_endash_range_is_range_endpoint() -> None:
    evs = enumerate_values("200–300 МПа")
    assert [e.value for e in evs] == [200.0, 300.0]
    assert all(e.kind == "range_endpoint" for e in evs)


def test_word_range_to_is_range_endpoint() -> None:
    evs = enumerate_values("2 to 4 h")
    assert [e.value for e in evs] == [2.0, 4.0]
    assert all(e.kind == "range_endpoint" for e in evs)


def test_word_range_do_is_range_endpoint() -> None:
    evs = enumerate_values("100 до 300 т/сут")
    assert [e.value for e in evs] == [100.0, 300.0]
    assert all(e.kind == "range_endpoint" for e in evs)


def test_decimal_comma_glued_is_single_number() -> None:
    # «2,5» — comma directly between digits is a decimal mark, not a list separator.
    evs = enumerate_values("2,5 %")
    assert len(evs) == 1
    assert evs[0].kind == "single"
    assert evs[0].value == 2.5


def test_three_or_more_with_dashes_falls_back_to_list() -> None:
    # Not a two-endpoint range: enumerate as discrete list points.
    evs = enumerate_values("180, 200, 220")
    assert [e.value for e in evs] == [180.0, 200.0, 220.0]
    assert all(e.kind == "list" for e in evs)


def test_as_dict_round_trip() -> None:
    ev = enumerate_values("150 HV")[0]
    assert ev.as_dict() == {
        "value": 150.0,
        "char_start": 0,
        "char_end": 3,
        "kind": "single",
    }


def test_frozen_dataclass_is_immutable() -> None:
    ev = EnumeratedValue(1.0, 0, 1, "single")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.value = 2.0  # type: ignore[misc]


def test_invalid_kind_rejected() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        EnumeratedValue(1.0, 0, 1, "bogus")
