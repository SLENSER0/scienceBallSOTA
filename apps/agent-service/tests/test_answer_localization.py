"""§13.17 tests: bilingual section-label localization for the six answer tabs."""

from __future__ import annotations

import orjson
from agent_service.answer_localization import (
    LABELS,
    SECTION_KEYS,
    label_for,
    localize_sections,
)


def test_label_for_summary_ru() -> None:
    """(1) ru summary label is the Russian word."""
    assert label_for("summary", "ru") == "Сводка"


def test_label_for_gaps_en() -> None:
    """(2) en gaps label is the English word."""
    assert label_for("gaps", "en") == "Gaps"


def test_unknown_language_falls_back_to_english() -> None:
    """(3) an unknown language 'de' falls back to the English label."""
    assert label_for("summary", "de") == "Summary"
    assert label_for("summary", "de") == LABELS["summary"]["en"]


def test_unknown_key_returns_key_unchanged() -> None:
    """(4) an unknown key returns the key string unchanged."""
    assert label_for("nonexistent", "ru") == "nonexistent"
    assert label_for("nonexistent", "en") == "nonexistent"


def test_localize_sections_has_six_keys_in_order() -> None:
    """(5) as_dict has exactly the six SECTION_KEYS in order."""
    result = localize_sections("ru").as_dict()
    assert tuple(result.keys()) == SECTION_KEYS
    assert len(result) == 6


def test_every_key_defines_ru_and_en() -> None:
    """(6) every key in LABELS defines both 'ru' and 'en'."""
    assert set(LABELS) == set(SECTION_KEYS)
    for key, translations in LABELS.items():
        assert set(translations) == {"ru", "en"}, key
        assert translations["ru"]
        assert translations["en"]


def test_as_dict_orjson_serialisable_preserves_order() -> None:
    """(7) as_dict is orjson-serialisable and preserves key order."""
    localized = localize_sections("ru")
    raw = orjson.dumps(localized.as_dict())
    round_tripped = orjson.loads(raw)
    assert tuple(round_tripped.keys()) == SECTION_KEYS
    assert round_tripped["summary"] == "Сводка"
    assert round_tripped["contradictions"] == "Противоречия"


def test_localize_sections_english_labels() -> None:
    """Sanity: en localization yields the English label table."""
    result = localize_sections("en").as_dict()
    assert result == {key: LABELS[key]["en"] for key in SECTION_KEYS}
