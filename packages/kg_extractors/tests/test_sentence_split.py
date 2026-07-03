"""Hand-checked tests for RU/EN sentence segmentation (§5.9)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_extractors.sentence_split import Sentence, split_sentences


def test_simple_two_sentences() -> None:
    """A plain EN pair splits into two, keeping the terminating dot (§5.9)."""
    sents = split_sentences("Hardness rose. Then it fell.")
    assert len(sents) == 2
    assert sents[0].text == "Hardness rose."
    assert sents[1].text == "Then it fell."


def test_offsets_are_exact() -> None:
    """Every sentence's offsets reproduce its text from the source (§5.9)."""
    text = "Hardness rose. Then it fell."
    for s in split_sentences(text):
        assert text[s.char_start : s.char_end] == s.text


def test_english_abbrev_before_digit_stays_one() -> None:
    """``Fig. 3`` is not a sentence end — one sentence (сокращение), §5.9."""
    assert len(split_sentences("See Fig. 3 for detail.")) == 1


def test_english_abbrev_before_capital_stays_one() -> None:
    """``Fig.`` before a capital still does not split (abbrev rule bites), §5.9."""
    sents = split_sentences("See Fig. Two facts remain.")
    assert len(sents) == 1
    assert sents[0].text == "See Fig. Two facts remain."


def test_decimal_number_stays_one() -> None:
    """A decimal ``5.0`` is not a boundary — one sentence (десятичное), §5.9."""
    assert len(split_sentences("The value was 5.0 MPa.")) == 1


def test_russian_two_sentences() -> None:
    """RU capitals trigger the split just like EN ones (§5.9)."""
    sents = split_sentences("Готово. Далее.")
    assert len(sents) == 2
    assert sents[0].text == "Готово."
    assert sents[1].text == "Далее."


def test_russian_abbrev_chain_stays_one() -> None:
    """``см. табл. 1`` chains two RU abbreviations — one sentence (§5.9)."""
    assert len(split_sentences("см. табл. 1 ниже.")) == 1


def test_russian_dotted_abbrev_te_stays_one() -> None:
    """The dotted ``т.е.`` before a capital does not split (§5.9)."""
    sents = split_sentences("Это т.е. Верно сказано.")
    assert len(sents) == 1


def test_empty_string_returns_empty_list() -> None:
    """Empty input yields no sentences (пустая строка), §5.9."""
    assert split_sentences("") == []


def test_unterminated_fragment_spans_whole_string() -> None:
    """A fragment without a terminator is one whole-span sentence (§5.9)."""
    text = "no period here"
    sents = split_sentences(text)
    assert len(sents) == 1
    assert sents[0].text == text
    assert sents[0].char_start == 0
    assert sents[0].char_end == len(text)
    assert text[sents[0].char_start : sents[0].char_end] == text


def test_offsets_exact_across_russian_and_abbrev() -> None:
    """Offset invariant holds even with RU text and internal abbreviations (§5.9)."""
    text = "См. рис. 2. Прочность выросла. Затем упала."
    for s in split_sentences(text):
        assert text[s.char_start : s.char_end] == s.text


def test_bang_and_question_terminators_split() -> None:
    """``!`` and ``?`` also open new sentences before a capital (§5.9)."""
    sents = split_sentences("Really? Yes! Absolutely.")
    assert [s.text for s in sents] == ["Really?", "Yes!", "Absolutely."]


def test_sentence_is_frozen() -> None:
    """:class:`Sentence` is immutable (frozen dataclass), §5.9."""
    s = Sentence(text="Hi.", char_start=0, char_end=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.text = "Bye."  # type: ignore[misc]


def test_as_dict_round_trips_fields() -> None:
    """``as_dict`` exposes all three fields verbatim (§5.9)."""
    s = Sentence(text="Готово.", char_start=0, char_end=7)
    assert s.as_dict() == {"text": "Готово.", "char_start": 0, "char_end": 7}
