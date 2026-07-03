"""Robust RU/EN sentence segmentation for soft-splitting chunks (§5.9).

Мягкое разбиение (§5.4) режет длинные абзацы по границам предложений, чтобы окно
эмбеддинга и промпт извлечения не рвали мысль посередине. A naive
"split on the dot" ruins this: it cuts decimals (``5.0`` → ``5`` + ``0``) and
breaks after abbreviations (``рис.``, ``Fig.``) that are not sentence ends.

:func:`split_sentences` splits on a terminator (``.`` ``!`` ``?`` ``…``) only when
it is followed by whitespace and then a capital letter — the classic
"end-of-sentence" signal that works for both Cyrillic and Latin capitals. It
suppresses the split when:

* the terminator closes a known RU/EN abbreviation (``рис.``, ``табл.``, ``т.е.``,
  ``т.д.``, ``см.``, ``Fig.``, ``Eq.``, ``e.g.``, ``i.e.``, ``vs.``, ``et al.``);
* the ``.`` sits inside a decimal number (``5.0``) — здесь после точки нет пробела,
  поэтому граница не срабатывает.

Each returned :class:`Sentence` carries exact character offsets into the *original*
string, so ``text[s.char_start:s.char_end] == s.text`` holds for every sentence
(смещения точные). Pure Python, stdlib only — no I/O, no third-party deps.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- sentence terminators (знаки конца предложения), §5.9 --------------------
TERMINATORS = frozenset({".", "!", "?", "…"})

#: Known RU+EN abbreviations whose trailing ``.`` is *not* a sentence end
#: (сокращения — точка не завершает предложение). Stored lower-cased; matched
#: case-insensitively as a whole-token suffix ending at the terminator.
ABBREVIATIONS = frozenset(
    {
        "рис.",
        "табл.",
        "т.е.",
        "т.д.",
        "см.",
        "fig.",
        "eq.",
        "e.g.",
        "i.e.",
        "vs.",
        "et al.",
    }
)


@dataclass(frozen=True)
class Sentence:
    """One segmented sentence with exact offsets into the source text (§5.9).

    Fields
    ------
    text
        The sentence string, trimmed of surrounding whitespace (текст предложения).
    char_start
        Inclusive start offset in the original text (начало), so
        ``text[char_start:char_end]`` reproduces :attr:`text` exactly.
    char_end
        Exclusive end offset in the original text (конец).
    """

    text: str
    char_start: int
    char_end: int

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


def _is_capital(ch: str) -> bool:
    """True if *ch* is a single upper-case letter, RU or EN (заглавная буква).

    ``str.isupper`` is script-agnostic: it holds for Latin ``T`` and Cyrillic ``Д``
    alike, and is ``False`` for digits, punctuation and whitespace.
    """
    return len(ch) == 1 and ch.isupper()


def _ends_with_abbrev(text: str, end: int) -> bool:
    """True if ``text[:end]`` ends with a known abbreviation as a whole token (§5.9).

    *end* points just past the terminating ``.``. A match must be preceded by a
    non-alphanumeric character (or the string start) so that ``planet al.`` does
    not masquerade as ``et al.`` (проверяем границу слова слева).
    """
    lowered = text[:end].lower()
    for abbr in ABBREVIATIONS:
        start = end - len(abbr)
        if start < 0:
            continue
        if lowered[start:end] != abbr:
            continue
        if start == 0 or not text[start - 1].isalnum():
            return True
    return False


def _is_boundary(text: str, i: int) -> bool:
    """True if a sentence boundary ends right after the terminator at index *i* (§5.9).

    Requires terminator → whitespace → capital, and rejects the split when the
    terminator closes a known abbreviation. Decimals (``5.0``) never qualify: no
    whitespace follows the dot, so the whitespace test fails first.
    """
    n = len(text)
    j = i + 1
    if j >= n or not text[j].isspace():  # need whitespace after terminator
        return False
    k = j
    while k < n and text[k].isspace():
        k += 1
    if k >= n or not _is_capital(text[k]):  # need a capital to open next sentence
        return False
    # A ``.`` closing a known abbreviation is not a sentence end (сокращение).
    return not (text[i] == "." and _ends_with_abbrev(text, i + 1))


def _trim(text: str, start: int, end: int) -> Sentence | None:
    """Trim surrounding whitespace of ``text[start:end]`` into a :class:`Sentence`.

    Returns ``None`` for a blank (whitespace-only) span (пустой фрагмент). Offsets
    are recomputed so ``text[cs:ce] == Sentence.text`` remains exact.
    """
    cs = start
    while cs < end and text[cs].isspace():
        cs += 1
    ce = end
    while ce > cs and text[ce - 1].isspace():
        ce -= 1
    if cs >= ce:
        return None
    return Sentence(text=text[cs:ce], char_start=cs, char_end=ce)


def split_sentences(text: str) -> list[Sentence]:
    """Segment *text* into sentences with exact char offsets (§5.9).

    Splits after ``.`` ``!`` ``?`` ``…`` when followed by whitespace and a capital
    letter, but never inside a decimal number or after a known RU/EN abbreviation.
    An empty string yields ``[]``; a single unterminated fragment yields one
    :class:`Sentence` spanning the whole string (одно предложение).
    """
    n = len(text)
    cuts: list[int] = []
    for i, ch in enumerate(text):
        if ch in TERMINATORS and _is_boundary(text, i):
            cuts.append(i + 1)  # sentence ends just past the terminator

    sentences: list[Sentence] = []
    prev = 0
    for cut in cuts:
        seg = _trim(text, prev, cut)
        if seg is not None:
            sentences.append(seg)
        prev = cut
    if prev < n:  # trailing fragment (may be unterminated)
        seg = _trim(text, prev, n)
        if seg is not None:
            sentences.append(seg)
    return sentences
