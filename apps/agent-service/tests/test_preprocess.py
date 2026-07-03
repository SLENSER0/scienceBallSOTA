"""Tests for the §13.7 preprocess node (§7.5 Node 1).

Deterministic, dependency-light: exercises language detection (ru/en/mixed/
unknown), Unicode normalization (NBSP, fancy quotes, en/em dashes, kept ≤/≥) and
the cheap intent flags (сравнение / пробел / has_numeric) on hand-checkable
RU/EN inputs.
"""

from __future__ import annotations

import dataclasses

import pytest
from agent_service.preprocess import PreprocessedQuery, preprocess_query


def test_language_ru() -> None:
    # Pure Cyrillic → 'ru'.
    pq = preprocess_query("Какие методы очистки сточных вод применяются?")
    assert pq.language == "ru"


def test_language_en() -> None:
    # Pure Latin → 'en'.
    pq = preprocess_query("Which wastewater treatment methods are used?")
    assert pq.language == "en"


def test_language_mixed() -> None:
    # ~16 Cyrillic vs ~17 Latin letters → ratio ~0.94 ≥ 0.35 → 'mixed'.
    pq = preprocess_query("Сравнить flotation и leaching для медь")
    assert pq.language == "mixed"


def test_language_stray_latin_stays_ru() -> None:
    # A single chemical symbol must not flip a Russian question to 'mixed'.
    pq = preprocess_query("Извлечение никеля Ni из раствора при выщелачивании")
    assert pq.language == "ru"


def test_empty_input_graceful() -> None:
    # Empty input → no crash, empty text, 'unknown', all flags False.
    pq = preprocess_query("")
    assert pq.text == ""
    assert pq.language == "unknown"
    assert not pq.is_comparison
    assert not pq.is_gap_intent
    assert not pq.has_numeric


def test_whitespace_only_graceful() -> None:
    # Whitespace/NBSP-only input collapses to empty and stays 'unknown'.
    pq = preprocess_query("   \t\n  ")
    assert pq.text == ""
    assert pq.language == "unknown"


def test_normalize_nbsp_and_collapse() -> None:
    # NBSP (U+00A0) and runs of spaces collapse to single ASCII spaces; trimmed.
    pq = preprocess_query("  сравни методы   очистки  ")
    assert pq.text == "сравни методы очистки"
    assert " " not in pq.text


def test_normalize_dashes_to_hyphen() -> None:
    # en dash, em dash and minus sign all fold to ASCII hyphen-minus.
    pq = preprocess_query("Al–Cu — aging − hardness")
    assert "–" not in pq.text
    assert "—" not in pq.text
    assert "−" not in pq.text
    assert pq.text == "Al-Cu - aging - hardness"


def test_normalize_fancy_quotes() -> None:
    # Curly double/single quotes and guillemets fold to straight ASCII quotes.
    pq = preprocess_query("метод “флотация” и «выщелачивание» это ’лучшее’")
    assert "“" not in pq.text and "”" not in pq.text
    assert "«" not in pq.text and "»" not in pq.text
    assert '"флотация"' in pq.text
    assert '"выщелачивание"' in pq.text


def test_inequalities_preserved() -> None:
    # ≤ / ≥ carry numeric-constraint meaning and must survive normalization.
    pq = preprocess_query("плотность тока ≥ 250 и pH ≤ 3")
    assert "≤" in pq.text
    assert "≥" in pq.text


def test_is_comparison_ru() -> None:
    pq = preprocess_query("сравни методы флотации и выщелачивания")
    assert pq.is_comparison is True
    assert pq.is_gap_intent is False


def test_is_comparison_en_vs() -> None:
    pq = preprocess_query("flotation vs leaching for copper recovery")
    assert pq.is_comparison is True


def test_is_gap_intent_probely() -> None:
    pq = preprocess_query("какие есть пробелы в исследованиях по этой теме?")
    assert pq.is_gap_intent is True
    assert pq.is_comparison is False


def test_is_gap_intent_net_dannyh() -> None:
    pq = preprocess_query("по каким режимам нет данных в базе?")
    assert pq.is_gap_intent is True


def test_has_numeric_with_unit() -> None:
    # Digits present (paired with unit А/м²) → has_numeric True.
    pq = preprocess_query("плотность тока 250 А/м²")
    assert pq.has_numeric is True


def test_has_numeric_false_without_digits() -> None:
    pq = preprocess_query("сравни методы очистки")
    assert pq.has_numeric is False


def test_as_dict_shape_and_frozen() -> None:
    pq = preprocess_query("сравни 2 метода")
    d = pq.as_dict()
    assert d == {
        "raw": "сравни 2 метода",
        "text": "сравни 2 метода",
        "language": "ru",
        "is_comparison": True,
        "is_gap_intent": False,
        "has_numeric": True,
    }
    # Frozen dataclass: attributes are immutable.
    assert isinstance(pq, PreprocessedQuery)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pq.language = "en"  # type: ignore[misc]
