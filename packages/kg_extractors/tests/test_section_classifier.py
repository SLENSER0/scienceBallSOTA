"""Section-heading classification for chunk-type routing (§5.9 / §9.2 Step 3)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.section_classifier import (
    SectionKind,
    SectionLabel,
    classify_path,
    classify_section,
    strip_numbering,
)


def test_english_abstract() -> None:
    assert classify_section("Abstract").kind == SectionKind.ABSTRACT


def test_numbered_materials_and_methods() -> None:
    label = classify_section("2.1 Materials and Methods")
    assert label.kind == SectionKind.METHODS
    assert label.matched_keyword is not None


def test_combined_results_and_discussion_picks_results() -> None:
    # "Результаты" precedes "обсуждение" → the leading section wins (раньше в строке).
    assert classify_section("Результаты и обсуждение").kind == SectionKind.RESULTS


def test_russian_references() -> None:
    assert classify_section("Список литературы").kind == SectionKind.REFERENCES


def test_unmatched_heading_is_other_with_no_keyword() -> None:
    label = classify_section("Weather report")
    assert label.kind == SectionKind.OTHER
    assert label.matched_keyword is None


def test_path_last_meaningful_segment_wins() -> None:
    assert classify_path(["Results", "Mechanical properties"]) == SectionKind.RESULTS


def test_path_skips_leading_other_segment() -> None:
    assert classify_path(["Random", "Methods"]) == SectionKind.METHODS


def test_as_dict_kind_is_plain_string() -> None:
    assert classify_section("Methods").as_dict()["kind"] == "methods"


def test_russian_keywords_hand_checked() -> None:
    cases = {
        "Аннотация": SectionKind.ABSTRACT,
        "Введение": SectionKind.INTRODUCTION,
        "Материалы и методы": SectionKind.METHODS,
        "Методика эксперимента": SectionKind.METHODS,
        "Результаты": SectionKind.RESULTS,
        "Обсуждение": SectionKind.DISCUSSION,
        "Выводы": SectionKind.CONCLUSION,
        "Заключение": SectionKind.CONCLUSION,
        "Благодарности": SectionKind.ACKNOWLEDGEMENTS,
    }
    for title, expected in cases.items():
        assert classify_section(title).kind == expected, title


def test_english_keywords_hand_checked() -> None:
    cases = {
        "Introduction": SectionKind.INTRODUCTION,
        "Methods": SectionKind.METHODS,
        "Results": SectionKind.RESULTS,
        "Discussion": SectionKind.DISCUSSION,
        "Conclusion": SectionKind.CONCLUSION,
        "References": SectionKind.REFERENCES,
        "Acknowledgements": SectionKind.ACKNOWLEDGEMENTS,
    }
    for title, expected in cases.items():
        assert classify_section(title).kind == expected, title


def test_case_insensitive_matching() -> None:
    assert classify_section("ABSTRACT").kind == SectionKind.ABSTRACT
    assert classify_section("introduction").kind == SectionKind.INTRODUCTION
    assert classify_section("рЕзУлЬтАтЫ").kind == SectionKind.RESULTS


def test_matched_keyword_is_the_lowercase_hit() -> None:
    assert classify_section("Abstract").matched_keyword == "abstract"
    assert classify_section("Список литературы").matched_keyword == "список литературы"


def test_strip_numbering_variants() -> None:
    assert strip_numbering("2.1 Methods") == "Methods"
    assert strip_numbering("3 Results") == "Results"
    assert strip_numbering("1.2.3. Discussion") == "Discussion"
    assert strip_numbering("4) Conclusion") == "Conclusion"
    # No trailing space after the digits → not treated as numbering (сохраняем).
    assert strip_numbering("40Х steel") == "40Х steel"
    assert strip_numbering("Methods") == "Methods"


def test_deeply_nested_path_uses_last_non_other() -> None:
    path = ["Introduction", "Background", "Methods", "Sample prep"]
    # "Sample prep" is OTHER, so the last meaningful segment is "Methods".
    assert classify_path(path) == SectionKind.METHODS


def test_all_other_path_returns_other() -> None:
    assert classify_path(["Random", "Weather report"]) == SectionKind.OTHER


def test_empty_path_returns_other() -> None:
    assert classify_path([]) == SectionKind.OTHER


def test_as_dict_round_trips_fields() -> None:
    label = classify_section("2.1 Materials and Methods")
    assert label.as_dict() == {
        "title": "2.1 Materials and Methods",
        "kind": "methods",
        "matched_keyword": label.matched_keyword,
    }
    assert set(label.as_dict()) == {"title", "kind", "matched_keyword"}


def test_section_kind_is_str_enum() -> None:
    # StrEnum members compare equal to their str value (сравнимы со строкой).
    assert SectionKind.METHODS == "methods"
    assert SectionKind.OTHER.value == "other"


def test_section_label_is_frozen() -> None:
    label = classify_section("Abstract")
    assert isinstance(label, SectionLabel)
    with pytest.raises(FrozenInstanceError):
        label.kind = SectionKind.OTHER  # type: ignore[misc]  # frozen is immutable
