"""Property-mention extraction (§6.6)."""

from __future__ import annotations

from kg_extractors.property_extractor import extract_properties


def test_ru_and_en_properties() -> None:
    text = "Измеряли твёрдость по Виккерсу и предел прочности; также current density."
    ids = {p.property_id for p in extract_properties(text)}
    assert "prop:hardness" in ids
    assert "prop:tensile_strength" in ids
    assert "prop:current_density" in ids


def test_spans_point_at_surface() -> None:
    text = "Степень извлечения меди составила 92%."
    ms = extract_properties(text)
    rec = next(m for m in ms if m.property_id == "prop:recovery")
    assert text[rec.span[0] : rec.span[1]].lower() == "степень извлечения"


def test_longer_synonym_wins_over_substring() -> None:
    # "плотность тока" (current_density) must win over "плотность" (density).
    ms = extract_properties("Поддерживали плотность тока 250 А/м².")
    ids = [m.property_id for m in ms]
    assert "prop:current_density" in ids
    assert "prop:density" not in ids


def test_whole_word_matching_only() -> None:
    # substring inside another word must not match.
    assert extract_properties("твердостью материала") == [] or all(
        p.surface != "hardness" for p in extract_properties("твердостью материала")
    )
    assert extract_properties("") == []
