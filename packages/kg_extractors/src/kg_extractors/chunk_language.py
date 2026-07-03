"""Per-chunk language tagging for the RU + EN corpus (§5.9).

Science-Ball ingests a bilingual corpus: Russian metallurgical handbooks
(``Твёрдость сплава``) sit next to English papers (``Alloy hardness``) and,
increasingly, chunks that quote both in one breath (``Al-Cu сплав hardness``).
Downstream extractors and vocabularies branch on language, so every chunk needs
a cheap, deterministic language tag *before* the LLM ever sees it.

The heuristic is pure script counting — no model, no I/O, stdlib only:

* count the Cyrillic letters and the Latin letters in the text;
* ``ru_fraction`` / ``en_fraction`` are those counts over the *total* letter
  count, each rounded to 2 decimal places;
* the label is :data:`Lang.RU` when Cyrillic makes up ``>= 0.7`` of the letters,
  :data:`Lang.EN` when Latin does, :data:`Lang.MIXED` when both scripts are
  present but neither dominates, and :data:`Lang.UNKNOWN` when the text carries
  no letters at all (digits, punctuation, whitespace).

Because the fractions are letters-of-that-script over *all* letters, a text in a
third script (say Greek) can leave ``ru_fraction + en_fraction < 1.0``; the sum
is never greater than ``1.0``.

Public API:

- :class:`Lang` — the four language labels as a :class:`~enum.StrEnum`;
- :class:`LangTag` — frozen ``(lang, ru_fraction, en_fraction)`` with
  :meth:`LangTag.as_dict`;
- :func:`detect_language` — tag a single text;
- :func:`tag_chunks` — map :func:`detect_language` over chunk dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: A script must reach this share of the letters to be the *dominant* one (порог).
DOMINANT_THRESHOLD = 0.7

# Unicode Cyrillic block U+0400–U+04FF covers RU incl. Ё/ё (кириллический блок).
_CYRILLIC_LO = 0x0400
_CYRILLIC_HI = 0x04FF


class Lang(StrEnum):
    """Language label attached to a chunk (§5.9).

    A :class:`~enum.StrEnum`, so a :class:`Lang` serializes as its bare string
    value (``"ru"``, ``"en"``, ``"mixed"``, ``"unknown"``) with no ``Lang.``
    prefix — ideal for JSON payloads and hand-checkable assertions.
    """

    RU = "ru"
    EN = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LangTag:
    """Language tag for one chunk of text (§5.9).

    Fields
    ------
    lang
        One of :class:`Lang` — the detected label (язык).
    ru_fraction
        Share of the text's letters that are Cyrillic, ``[0, 1]`` rounded to
        2 dp (доля кириллицы); ``0.0`` when the text has no letters.
    en_fraction
        Share of the text's letters that are Latin, ``[0, 1]`` rounded to 2 dp
        (доля латиницы); ``0.0`` when the text has no letters. Since both
        fractions are taken over *all* letters, ``ru_fraction + en_fraction``
        never exceeds ``1.0``.
    """

    lang: Lang
    ru_fraction: float
    en_fraction: float

    def as_dict(self) -> dict[str, object]:
        """Full structured view with ``lang`` as a plain string (все поля)."""
        return {
            "lang": str(self.lang),
            "ru_fraction": self.ru_fraction,
            "en_fraction": self.en_fraction,
        }


def _is_cyrillic(ch: str) -> bool:
    """True if *ch* is a single Cyrillic letter (кириллическая буква), §5.9."""
    return ch.isalpha() and _CYRILLIC_LO <= ord(ch) <= _CYRILLIC_HI


def _is_latin(ch: str) -> bool:
    """True if *ch* is a single ASCII Latin letter A–Z / a–z (латиница), §5.9."""
    return ch.isalpha() and ("A" <= ch <= "Z" or "a" <= ch <= "z")


def detect_language(text: str) -> LangTag:
    """Tag *text* as ru / en / mixed / unknown by script counting (§5.9).

    Counts Cyrillic vs Latin letters over the *total* letter count. The label is
    :data:`Lang.RU` when Cyrillic reaches :data:`DOMINANT_THRESHOLD` of the
    letters, :data:`Lang.EN` when Latin does, :data:`Lang.MIXED` when both
    scripts appear but neither dominates, and :data:`Lang.UNKNOWN` when there are
    no letters at all. Fractions are rounded to 2 decimal places.
    """
    cyrillic = 0
    latin = 0
    letters = 0
    for ch in text:
        if not ch.isalpha():
            continue
        letters += 1
        if _is_cyrillic(ch):
            cyrillic += 1
        elif _is_latin(ch):
            latin += 1

    if letters == 0:
        return LangTag(lang=Lang.UNKNOWN, ru_fraction=0.0, en_fraction=0.0)

    ru_fraction = round(cyrillic / letters, 2)
    en_fraction = round(latin / letters, 2)

    if cyrillic / letters >= DOMINANT_THRESHOLD:
        lang = Lang.RU
    elif latin / letters >= DOMINANT_THRESHOLD:
        lang = Lang.EN
    elif cyrillic > 0 and latin > 0:
        lang = Lang.MIXED
    else:
        # Only a non-RU/EN script (e.g. Greek) is present: no dominant Latin or
        # Cyrillic and not both together (только сторонний алфавит).
        lang = Lang.UNKNOWN

    return LangTag(lang=lang, ru_fraction=ru_fraction, en_fraction=en_fraction)


def tag_chunks(chunks: list[dict]) -> list[LangTag]:
    """Tag every chunk dict by its ``text`` key, in input order (§5.9).

    Each element must carry a ``text`` field (the chunk contract's payload);
    :func:`detect_language` is applied to it. Missing ``text`` is treated as an
    empty string, i.e. :data:`Lang.UNKNOWN`.
    """
    return [detect_language(chunk.get("text", "")) for chunk in chunks]
