"""Tests for the §19.6 unicode obfuscation normalizer.

Проверяем удаление нулевой ширины символов и отображение «двойников» в ASCII.
"""

from __future__ import annotations

from kg_common.security.injection_normalize import (
    NormalizeResult,
    map_homoglyphs,
    normalize_text,
    strip_zero_width,
)

ZWSP = "​"  # zero-width space
CYRILLIC_O = "о"  # look-alike of ASCII 'o'
FULLWIDTH_A = "Ａ"  # 'Ａ' look-alike of ASCII 'A'


def test_zero_width_between_words_removed() -> None:
    # Assertion (1): one ZWSP splitting 'ignore previous'.
    result = normalize_text(f"ignore{ZWSP} previous")
    assert result.removed_zero_width == 1
    assert result.text == "ignore previous"


def test_result_text_has_no_zero_width() -> None:
    # Assertion (2): output never retains U+200B.
    result = normalize_text(f"foo{ZWSP}bar")
    assert ZWSP not in result.text


def test_cyrillic_o_in_ignore_folded_to_ascii() -> None:
    # Assertion (3): 'ignore' spelled with a Cyrillic 'о' folds to ASCII.
    obfuscated = "ign" + CYRILLIC_O + "re"
    assert obfuscated != "ignore"  # genuinely non-ASCII input
    assert map_homoglyphs(obfuscated) == "ignore"
    result = normalize_text(obfuscated)
    assert result.text == "ignore"
    assert result.homoglyphs_mapped > 0


def test_clean_ascii_unchanged() -> None:
    # Assertion (4): a clean ASCII string is untouched.
    result = normalize_text("ignore previous instructions")
    assert result.changed is False
    assert result.removed_zero_width == 0
    assert result.homoglyphs_mapped == 0
    assert result.text == "ignore previous instructions"


def test_two_zero_width_chars_counted() -> None:
    # Assertion (5): two zero-width chars → count of 2.
    result = normalize_text(f"a{ZWSP}b⁠c")
    assert result.removed_zero_width == 2
    assert result.text == "abc"


def test_fullwidth_a_maps_to_ascii() -> None:
    # Assertion (6): fullwidth 'Ａ' → 'A'.
    assert map_homoglyphs(FULLWIDTH_A) == "A"
    result = normalize_text(FULLWIDTH_A)
    assert result.text == "A"
    assert result.homoglyphs_mapped == 1


def test_changed_iff_text_differs() -> None:
    # Assertion (7): changed is True exactly when output differs from input.
    clean = normalize_text("plain text")
    assert clean.changed is False
    dirty = normalize_text(f"plain{ZWSP}text")
    assert dirty.changed is True
    assert dirty.changed == (dirty.text != "plain​text")


def test_as_dict_exposes_counts() -> None:
    # Assertion (8): as_dict() surfaces both counts.
    result = normalize_text(f"ign{CYRILLIC_O}re{ZWSP}")
    d = result.as_dict()
    assert d["removed_zero_width"] == 1
    assert d["homoglyphs_mapped"] == 1
    assert set(d) == {"text", "removed_zero_width", "homoglyphs_mapped", "changed"}


def test_strip_zero_width_pure() -> None:
    # strip_zero_width does not mutate and covers all listed code points.
    src = "x​‌‍⁠﻿y"
    assert strip_zero_width(src) == "xy"
    assert src == "x​‌‍⁠﻿y"  # unchanged input


def test_result_is_frozen() -> None:
    # Frozen dataclass contract.
    result = NormalizeResult(text="a", removed_zero_width=0, homoglyphs_mapped=0, changed=False)
    import dataclasses

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        result.text = "b"  # type: ignore[misc]
