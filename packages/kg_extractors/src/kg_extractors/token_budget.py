"""Token-budget soft splitter for oversized paragraphs — §5.9.

The char-based chunker (§5.9, :mod:`~kg_extractors.chunk_contract`) cuts a
document into chunks by character length. Some paragraphs are still too long for
a downstream token budget (an LLM context window, an embedding model). This
module does the complementary *soft* split (**«мягкое разбиение по
предложениям»**): it repacks a single oversized paragraph into pieces of at most
``max_tokens`` tokens, cutting **at sentence boundaries** so no sentence is torn
in half — and never losing a word of the input.

Token estimate
--------------
:func:`estimate_tokens` is a cheap, deterministic, stdlib-``re`` proxy for a real
tokenizer: it counts **word and number runs** in both Russian and English
(``[^\\W\\d_]+`` letter runs plus ``\\d+`` digit runs). Punctuation and
whitespace carry no tokens, so ``estimate_tokens('hello world') == 2`` and
``estimate_tokens('привет мир') == 2``.

Packing rules
-------------
* Split the paragraph into sentences at ``. ! ?`` boundaries, keeping each
  sentence's original text and trailing whitespace intact.
* Greedily pack whole sentences into a piece while the running token count stays
  ``<= max_tokens``; start a new piece when the next sentence would overflow.
* A **single sentence that alone exceeds** ``max_tokens`` cannot be packed
  whole, so it is *hard-split* into word groups of at most ``max_tokens`` tokens
  (with optional ``overlap_tokens`` carried between the groups).
* Every returned piece therefore satisfies ``tokens <= max_tokens``, and (with
  the default ``overlap_tokens=0``) concatenating the piece texts reproduces
  every word of the input in order.

Pure Python — stdlib only, no LLM, no I/O.

Public API:

- :func:`estimate_tokens` — RU+EN word/number token count;
- :class:`BudgetPiece`   — frozen ``(index, text, tokens)`` with :meth:`as_dict`;
- :func:`split_to_budget` — repack a paragraph into ``<= max_tokens`` pieces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A "token" for the estimate: a run of Unicode letters (RU+EN, no digits) or a
# run of digits. Underscores/punctuation/whitespace are boundaries, not tokens.
_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)

# A sentence: text up to (and including) a run of «.», «!» or «?», or the tail
# of the paragraph, plus any trailing whitespace so the raw text round-trips.
_SENTENCE_RE = re.compile(r"\S.*?(?:[.!?]+|$)(?:\s+|$)", re.DOTALL)


def estimate_tokens(text: str) -> int:
    """Count word + number tokens in ``text`` (RU+EN), stdlib ``re`` only.

    A token is a maximal run of Unicode letters or a maximal run of digits;
    punctuation and whitespace are boundaries and count for nothing. This is a
    tokenizer-free proxy for a token budget (оценка числа токенов).

    Examples
    --------
    ``estimate_tokens('hello world') == 2``; ``estimate_tokens('привет мир')
    == 2``; ``estimate_tokens('') == 0``.
    """
    return len(_TOKEN_RE.findall(text))


@dataclass(frozen=True)
class BudgetPiece:
    """One token-budget-bounded piece of a split paragraph (§5.9).

    Fields
    ------
    index
        0-based position of this piece in the emitted sequence (номер куска).
    text
        The piece's text, stripped of leading/trailing whitespace (текст).
    tokens
        ``estimate_tokens(text)`` — always ``<= max_tokens`` for the split that
        produced it (число токенов).
    """

    index: int
    text: str
    tokens: int

    def as_dict(self) -> dict[str, object]:
        """Return the canonical JSON-ready mapping for this piece."""
        return {"index": self.index, "text": self.text, "tokens": self.tokens}


def _split_sentences(text: str) -> list[str]:
    """Split ``text`` into raw sentence substrings (trailing whitespace kept).

    Concatenating the result reproduces ``text`` exactly, so no character is
    lost; boundaries are runs of «.», «!» or «?» (разбиение по предложениям).
    """
    return [m.group(0) for m in _SENTENCE_RE.finditer(text)]


def _hard_split(sentence: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Break a single over-budget ``sentence`` into ``<= max_tokens`` word groups.

    Words are the :func:`estimate_tokens` runs, joined by single spaces. With
    ``overlap_tokens`` the window steps by ``max_tokens - overlap_tokens`` so the
    tail of one group repeats at the head of the next (жёсткое дробление).
    """
    words = _TOKEN_RE.findall(sentence)
    if not words:
        return []
    step = max(1, max_tokens - overlap_tokens)
    pieces: list[str] = []
    i = 0
    while i < len(words):
        pieces.append(" ".join(words[i : i + max_tokens]))
        if i + max_tokens >= len(words):
            break
        i += step
    return pieces


def split_to_budget(text: str, max_tokens: int, overlap_tokens: int = 0) -> list[BudgetPiece]:
    """Repack ``text`` into pieces of at most ``max_tokens`` tokens (§5.9).

    Whole sentences are greedily packed (soft split «по предложениям»); a
    sentence that alone exceeds ``max_tokens`` is hard-split into word groups.
    Returns ``[]`` for empty/whitespace-only ``text``. Every piece has
    ``tokens <= max_tokens``; with ``overlap_tokens == 0`` the concatenated
    piece texts preserve every word of the input in order.

    Raises
    ------
    ValueError
        If ``max_tokens < 1`` or ``overlap_tokens`` is negative / ``>=
        max_tokens``.
    """
    if max_tokens < 1:
        raise ValueError("max_tokens must be >= 1")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must satisfy 0 <= overlap_tokens < max_tokens")
    if not text.strip():
        return []

    raw_pieces: list[str] = []
    current = ""
    current_tokens = 0
    for sentence in _split_sentences(text):
        stoks = estimate_tokens(sentence)
        if stoks > max_tokens:
            if current:
                raw_pieces.append(current)
                current, current_tokens = "", 0
            raw_pieces.extend(_hard_split(sentence, max_tokens, overlap_tokens))
            continue
        if current and current_tokens + stoks > max_tokens:
            raw_pieces.append(current)
            current, current_tokens = "", 0
        current += sentence
        current_tokens += stoks
    if current:
        raw_pieces.append(current)

    pieces: list[BudgetPiece] = []
    for index, raw in enumerate(raw_pieces):
        stripped = raw.strip()
        pieces.append(BudgetPiece(index=index, text=stripped, tokens=estimate_tokens(stripped)))
    return pieces
