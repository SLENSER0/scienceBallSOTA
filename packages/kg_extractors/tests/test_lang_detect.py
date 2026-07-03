"""Lightweight RU/EN language detection by letter script ratio (§5.11)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.lang_detect import (
    LANG_EN,
    LANG_MIXED,
    LANG_RU,
    LANG_UNKNOWN,
    LangResult,
    detect_language,
    is_cyrillic,
)


def test_ru_text_is_ru_with_high_ru_ratio() -> None:
    # Pure Russian sentence — every letter is Cyrillic (все буквы кириллические).
    res = detect_language("Химический анализ образца показал высокое содержание.")
    assert res.lang == LANG_RU
    assert res.ru_ratio == 1.0
    assert res.en_ratio == 0.0
    assert res.confidence == 1.0


def test_en_text_is_en_with_high_en_ratio() -> None:
    res = detect_language("The quick brown fox jumps over the lazy dog.")
    assert res.lang == LANG_EN
    assert res.en_ratio == 1.0
    assert res.ru_ratio == 0.0
    assert res.confidence == 1.0


def test_mixed_ru_en_is_mixed() -> None:
    # "привет"(6) + "мир"(3) = 9 Cyrillic; "hello"(5) + "world"(5) = 10 Latin.
    res = detect_language("привет hello мир world")
    assert res.lang == LANG_MIXED
    assert res.ru_ratio == pytest.approx(9 / 19)
    assert res.en_ratio == pytest.approx(10 / 19)
    assert 0.0 <= res.confidence <= 1.0


def test_digits_and_punct_only_is_unknown() -> None:
    res = detect_language("12345 !!! ... 3.14 %#@ -=+")
    assert res.lang == LANG_UNKNOWN
    assert res.ru_ratio == 0.0
    assert res.en_ratio == 0.0
    assert res.confidence == 0.0


def test_empty_is_unknown() -> None:
    res = detect_language("")
    assert res.lang == LANG_UNKNOWN
    assert res.ru_ratio == 0.0
    assert res.en_ratio == 0.0
    assert res.confidence == 0.0


def test_ratios_sum_sensibly() -> None:
    # With any letters present the two ratios partition the letters → sum to 1.0.
    for text in ("привет hello", "Сталь grade 45", "abc где", "The лаборатория"):
        res = detect_language(text)
        assert res.ru_ratio + res.en_ratio == pytest.approx(1.0)
    # No letters → both ratios are exactly zero (sum 0.0), not NaN.
    none = detect_language("2024-07-03")
    assert none.ru_ratio + none.en_ratio == 0.0


def test_confidence_always_in_unit_interval() -> None:
    samples = (
        "",
        "1234567890",
        "Полностью русский текст без латиницы",
        "Fully English text without any Cyrillic",
        "привет hello мир world",
        "Сталь 40Х ГОСТ 4543",
        "x",
        "ы",
    )
    for text in samples:
        assert 0.0 <= detect_language(text).confidence <= 1.0


def test_dominant_threshold_boundary() -> None:
    # 8 Cyrillic vs 2 Latin → ru_ratio 0.8 > 0.7 → ru (кириллица доминирует).
    ru_dominant = detect_language("абвгдежз yz")
    assert ru_dominant.lang == LANG_RU
    assert ru_dominant.ru_ratio == pytest.approx(0.8)
    # 7 Cyrillic vs 3 Latin → ru_ratio exactly 0.7, NOT > 0.7 → mixed (ровно порог).
    on_threshold = detect_language("абвгдеж xyz")
    assert on_threshold.lang == LANG_MIXED
    assert on_threshold.ru_ratio == pytest.approx(0.7)


def test_is_cyrillic_hand_checked() -> None:
    for ch in ("П", "я", "Ё", "ё", "щ", "Ж"):
        assert is_cyrillic(ch) is True
    for ch in ("A", "z", "Q", "1", " ", ".", "", "аб", "5"):
        assert is_cyrillic(ch) is False


def test_as_dict_round_trips_fields() -> None:
    res = detect_language("привет hello мир world")
    assert res.as_dict() == {
        "lang": res.lang,
        "ru_ratio": res.ru_ratio,
        "en_ratio": res.en_ratio,
        "confidence": res.confidence,
    }
    assert set(res.as_dict()) == {"lang", "ru_ratio", "en_ratio", "confidence"}


def test_lang_result_is_frozen() -> None:
    res = detect_language("текст")
    assert isinstance(res, LangResult)
    with pytest.raises(FrozenInstanceError):
        res.lang = LANG_EN  # type: ignore[misc]  # frozen dataclass is immutable
