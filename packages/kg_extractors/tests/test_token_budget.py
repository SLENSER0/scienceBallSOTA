"""Token-budget soft splitter tests — §5.9.

Hand-checked expectations for the sentence-boundary repacker: the RU+EN token
estimate, the empty/short-text edge cases, the ``tokens <= max_tokens``
invariant, a two-sentence split at the «.» boundary, the hard-split of a lone
over-budget sentence, and the word-preserving round-trip.
"""

from __future__ import annotations

from kg_extractors.token_budget import (
    BudgetPiece,
    estimate_tokens,
    split_to_budget,
)


def _words(text: str) -> list[str]:
    """The token words of ``text`` in order (mirror of estimate_tokens)."""
    import re

    return re.findall(r"[^\W\d_]+|\d+", text, re.UNICODE)


def test_estimate_tokens_en_ru_and_empty() -> None:
    assert estimate_tokens("hello world") == 2
    assert estimate_tokens("привет мир") == 2
    assert estimate_tokens("") == 0
    # Digits count as their own token; punctuation is free.
    assert estimate_tokens("Yield 350 MPa!") == 3


def test_empty_and_whitespace_yield_no_pieces() -> None:
    assert split_to_budget("", 5) == []
    assert split_to_budget("   \n\t ", 5) == []


def test_short_text_is_one_piece_equal_to_stripped_input() -> None:
    text = "  Hello world.  "
    pieces = split_to_budget(text, 10)
    assert len(pieces) == 1
    assert pieces[0].text == text.strip()
    assert pieces[0].index == 0
    assert pieces[0].tokens == 2


def test_every_piece_within_budget() -> None:
    text = "Alpha beta gamma. Delta epsilon. Zeta eta theta iota kappa lambda."
    for max_tokens in (1, 2, 3, 5, 7):
        pieces = split_to_budget(text, max_tokens)
        assert pieces, f"expected pieces for max_tokens={max_tokens}"
        for p in pieces:
            assert p.tokens <= max_tokens


def test_two_sentences_split_at_dot_boundary() -> None:
    # "Hello world." = 2 tokens, "Foo bar." = 2 tokens; budget 2 keeps each
    # sentence whole but forbids packing both together -> exactly 2 pieces.
    pieces = split_to_budget("Hello world. Foo bar.", 2)
    assert len(pieces) == 2
    assert pieces[0].text == "Hello world."
    assert pieces[1].text == "Foo bar."
    assert [p.index for p in pieces] == [0, 1]


def test_lone_over_budget_sentence_is_hard_split() -> None:
    # One sentence, no internal boundary, 6 tokens, budget 2 -> >1 piece.
    pieces = split_to_budget("one two three four five six", 2)
    assert len(pieces) > 1
    for p in pieces:
        assert p.tokens <= 2


def test_concatenation_preserves_every_word_in_order() -> None:
    text = (
        "Первое предложение про сталь. The alloy contains 12 percent chromium "
        "and shows high strength. Третье короткое."
    )
    pieces = split_to_budget(text, 4)
    joined = " ".join(p.text for p in pieces)
    assert _words(joined) == _words(text)


def test_as_dict_shape() -> None:
    piece = BudgetPiece(index=3, text="Foo bar", tokens=2)
    assert piece.as_dict() == {"index": 3, "text": "Foo bar", "tokens": 2}


def test_pieces_are_reindexed_contiguously() -> None:
    text = "aa bb cc. dd ee ff. gg hh ii."
    pieces = split_to_budget(text, 2)
    assert [p.index for p in pieces] == list(range(len(pieces)))
