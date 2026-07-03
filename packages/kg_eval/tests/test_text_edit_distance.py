"""OCR/parse edit-distance metrics — тесты расстояния редактирования (§23.34)."""

from __future__ import annotations

import pytest

from kg_eval.text_edit_distance import (
    EditDistanceReport,
    char_error_rate,
    levenshtein,
    score,
    word_error_rate,
)


def test_levenshtein_kitten_sitting() -> None:
    # Classic textbook distance: k→s, e→i, +g == 3 edits.
    assert levenshtein("kitten", "sitting") == 3


def test_levenshtein_identical_is_zero() -> None:
    assert levenshtein("abc", "abc") == 0


def test_levenshtein_symmetric() -> None:
    assert levenshtein("kitten", "sitting") == levenshtein("sitting", "kitten")


def test_levenshtein_empty_side() -> None:
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "") == 3
    assert levenshtein("", "") == 0


def test_char_error_rate_one_of_four() -> None:
    # One substituted char (c→x) out of four gold chars.
    assert char_error_rate("abcd", "abxd") == 0.25


def test_char_error_rate_empty_gold() -> None:
    assert char_error_rate("", "") == 0.0
    assert char_error_rate("", "xyz") == 1.0


def test_word_error_rate_one_of_three() -> None:
    # One substituted word (b→x) out of three gold tokens.
    assert word_error_rate("a b c", "a x c") == pytest.approx(1 / 3)


def test_word_error_rate_identical() -> None:
    assert word_error_rate("the cat sat", "the cat sat") == 0.0


def test_word_error_rate_empty_gold() -> None:
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "a b") == 1.0


def test_word_error_rate_extra_whitespace_ignored() -> None:
    # split() collapses runs of whitespace, so padding does not add tokens.
    assert word_error_rate("the cat sat", "  the   cat  sat ") == 0.0


def test_score_both_empty_similarity_one() -> None:
    r = score("", "")
    assert r.similarity == 1.0
    assert r.cer == 0.0
    assert r.wer == 0.0
    assert r.char_edits == 0
    assert r.gold_len == 0
    assert r.pred_len == 0


def test_score_identical() -> None:
    r = score("cat", "cat")
    assert r.cer == 0.0
    assert r.similarity == 1.0
    assert r.char_edits == 0
    assert r.wer == 0.0


def test_score_deletion() -> None:
    # "abc" -> "ab": one deletion; similarity normalised by longer len (3).
    r = score("abc", "ab")
    assert r.char_edits == 1
    assert r.similarity == pytest.approx(2 / 3)
    assert r.gold_len == 3
    assert r.pred_len == 2


def test_score_is_frozen_dataclass() -> None:
    r = score("abc", "ab")
    assert isinstance(r, EditDistanceReport)
    with pytest.raises((AttributeError, TypeError)):
        r.char_edits = 5  # type: ignore[misc]


def test_as_dict_stable_keys() -> None:
    d = score("abc", "abx").as_dict()
    assert set(d) == {"gold_len", "pred_len", "char_edits", "cer", "wer", "similarity"}
    assert d["char_edits"] == 1
    assert d["cer"] == pytest.approx(1 / 3)
