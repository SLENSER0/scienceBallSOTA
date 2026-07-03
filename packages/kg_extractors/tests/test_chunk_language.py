"""Tests for per-chunk RU/EN language tagging (§5.9)."""

from __future__ import annotations

from kg_extractors.chunk_language import (
    Lang,
    LangTag,
    detect_language,
    tag_chunks,
)


def test_pure_russian_is_ru() -> None:
    """A Russian phrase is RU with an overwhelming Cyrillic fraction (§5.9)."""
    tag = detect_language("Твёрдость сплава")
    assert tag.lang is Lang.RU
    assert tag.lang == "ru"  # StrEnum serializes to its bare value
    assert tag.ru_fraction >= 0.9
    assert tag.en_fraction == 0.0


def test_pure_english_is_en() -> None:
    """A Latin-only phrase is EN with a dominant Latin fraction (§5.9)."""
    tag = detect_language("Alloy hardness")
    assert tag.lang is Lang.EN
    assert tag.en_fraction >= 0.9
    assert tag.ru_fraction == 0.0


def test_bilingual_phrase_is_mixed() -> None:
    """Both scripts present, neither dominant -> MIXED (§5.9)."""
    tag = detect_language("Al-Cu сплав hardness твёрдость alloy")
    assert tag.lang is Lang.MIXED
    assert tag.ru_fraction > 0.0
    assert tag.en_fraction > 0.0


def test_letterless_text_is_unknown() -> None:
    """Digits and punctuation carry no letters -> UNKNOWN, zero fractions (§5.9)."""
    tag = detect_language("148 ±3")
    assert tag.lang is Lang.UNKNOWN
    assert tag.ru_fraction == 0.0
    assert tag.en_fraction == 0.0


def test_balanced_two_word_mix_is_mixed() -> None:
    """A 50/50 word mix 'cat кот' is MIXED with equal fractions (§5.9)."""
    tag = detect_language("cat кот")
    assert tag.lang is Lang.MIXED
    # 3 Latin + 3 Cyrillic out of 6 letters.
    assert tag.ru_fraction == 0.5
    assert tag.en_fraction == 0.5


def test_seven_ten_split_is_dominant_ru() -> None:
    """Exactly the 0.7 threshold of Cyrillic counts as dominant RU (§5.9)."""
    # 7 Cyrillic + 3 Latin = 10 letters -> ru_fraction 0.7 (== threshold).
    tag = detect_language("ббббббб abc")
    assert tag.ru_fraction == 0.7
    assert tag.en_fraction == 0.3
    assert tag.lang is Lang.RU


def test_fractions_never_exceed_one() -> None:
    """ru_fraction + en_fraction <= 1.0 for every kind of input (§5.9)."""
    samples = [
        "Твёрдость сплава",
        "Alloy hardness",
        "Al-Cu сплав hardness твёрдость alloy",
        "148 ±3",
        "",
        "cat кот",
        "αβγ δεζ",  # Greek only: neither RU nor EN
        "αβγ cat кот 42",
    ]
    for text in samples:
        tag = detect_language(text)
        assert tag.ru_fraction + tag.en_fraction <= 1.0
        assert tag.ru_fraction >= 0.0
        assert tag.en_fraction >= 0.0


def test_third_script_only_is_unknown() -> None:
    """Greek letters alone are neither RU nor EN and do not dominate -> UNKNOWN."""
    tag = detect_language("αβγ δεζ")
    assert tag.lang is Lang.UNKNOWN
    assert tag.ru_fraction == 0.0
    assert tag.en_fraction == 0.0


def test_empty_text_as_dict() -> None:
    """Empty input is UNKNOWN and as_dict() renders lang as a plain string (§5.9)."""
    tag = detect_language("")
    assert tag.lang is Lang.UNKNOWN
    d = tag.as_dict()
    assert d == {"lang": "unknown", "ru_fraction": 0.0, "en_fraction": 0.0}
    assert isinstance(d["lang"], str)


def test_langtag_is_frozen() -> None:
    """LangTag is an immutable frozen dataclass (§5.9)."""
    tag = LangTag(lang=Lang.EN, ru_fraction=0.0, en_fraction=1.0)
    try:
        tag.lang = Lang.RU  # type: ignore[misc]
    except Exception as exc:  # dataclasses.FrozenInstanceError
        assert "cannot assign" in str(exc) or "FrozenInstance" in type(exc).__name__
    else:  # pragma: no cover
        raise AssertionError("LangTag must be frozen")


def test_tag_chunks_maps_over_text_key() -> None:
    """tag_chunks reads each chunk's 'text' key, preserving order (§5.9)."""
    tags = tag_chunks([{"text": "Alloy"}])
    assert tags[0].lang is Lang.EN
    tags = tag_chunks([{"text": "Alloy"}, {"text": "Сплав"}, {"text": "148 ±3"}])
    assert [t.lang for t in tags] == [Lang.EN, Lang.RU, Lang.UNKNOWN]


def test_tag_chunks_missing_text_is_unknown() -> None:
    """A chunk dict without a 'text' key defaults to empty -> UNKNOWN (§5.9)."""
    tags = tag_chunks([{}])
    assert tags[0].lang is Lang.UNKNOWN


def test_rounding_to_two_dp() -> None:
    """Fractions are rounded to 2 decimal places (§5.9)."""
    # 1 Cyrillic + 2 Latin = 3 letters -> 1/3 = 0.33, 2/3 = 0.67.
    tag = detect_language("бab")
    assert tag.ru_fraction == 0.33
    assert tag.en_fraction == 0.67
    assert tag.lang is Lang.MIXED
