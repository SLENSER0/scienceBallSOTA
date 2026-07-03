"""Lightweight RU/EN language detection by letter script ratio (§5.11).

Извлечение (§5) часто смешивает русские и английские фрагменты в одном документе
(термины, единицы, названия методов). Before we route a chunk to a language-aware
tokenizer, prompt template, or stop-word list, we need a cheap, dependency-free
guess at *what language it is*. This module answers that with
:func:`detect_language`, which counts Cyrillic vs. Latin *letters* and reports:

* ``ru`` — Cyrillic dominates (доля кириллицы ``> 0.7``);
* ``en`` — Latin dominates (доля латиницы ``> 0.7``);
* ``mixed`` — both scripts are substantial, neither above the threshold (смесь);
* ``unknown`` — no letters at all: digits, punctuation, whitespace, or empty.

The result is a frozen :class:`LangResult` carrying the chosen ``lang`` plus the
two script ratios (which sum to ``1.0`` whenever any letter is present, else both
``0.0``) and a ``confidence`` in ``[0, 1]``. Pure Python, stdlib only — no I/O and
no third-party dependencies (только стандартная библиотека).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- language tokens (метки языка), §5.11 ------------------------------------
LANG_RU = "ru"
LANG_EN = "en"
LANG_MIXED = "mixed"
LANG_UNKNOWN = "unknown"

#: A script must exceed this share of letters to be called *dominant* (порог).
DOMINANT_THRESHOLD = 0.7

# Unicode Cyrillic block U+0400–U+04FF covers RU incl. Ё/ё (кириллический блок).
_CYRILLIC_LO = 0x0400
_CYRILLIC_HI = 0x04FF


@dataclass(frozen=True)
class LangResult:
    """Detected language of a text fragment (§5.11).

    Fields
    ------
    lang
        One of ``LANG_RU`` / ``LANG_EN`` / ``LANG_MIXED`` / ``LANG_UNKNOWN`` (язык).
    ru_ratio
        Share of letters that are Cyrillic, ``[0, 1]`` (доля кириллицы). ``0.0``
        when the text has no letters.
    en_ratio
        Share of letters that are Latin, ``[0, 1]`` (доля латиницы). Together with
        ``ru_ratio`` it sums to ``1.0`` whenever any letter is present, else ``0.0``.
    confidence
        How strongly the evidence supports ``lang``, ``[0, 1]`` (уверенность):
        the dominant ratio for ``ru``/``en``, ``2 * min(ratio)`` for a balanced
        ``mixed``, and ``0.0`` for ``unknown``.
    """

    lang: str
    ru_ratio: float
    en_ratio: float
    confidence: float

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "lang": self.lang,
            "ru_ratio": self.ru_ratio,
            "en_ratio": self.en_ratio,
            "confidence": self.confidence,
        }


def is_cyrillic(ch: str) -> bool:
    """True if *ch* is a single Cyrillic letter (кириллическая буква), §5.11.

    Non-letters inside the block (combining marks) and multi-character or empty
    strings are rejected (учитываем только буквы).
    """
    return len(ch) == 1 and ch.isalpha() and _CYRILLIC_LO <= ord(ch) <= _CYRILLIC_HI


def _is_latin(ch: str) -> bool:
    """True if *ch* is a single ASCII Latin letter ``a``–``z`` / ``A``–``Z`` (латиница)."""
    return len(ch) == 1 and ch.isascii() and ch.isalpha()


def detect_language(text: str) -> LangResult:
    """Classify *text* as RU/EN/mixed/unknown by its Cyrillic-vs-Latin letters (§5.11).

    Only letters count toward the ratios; digits, punctuation and whitespace are
    ignored (только буквы формируют доли). A script wins when its share of letters
    exceeds :data:`DOMINANT_THRESHOLD`; when neither does but letters exist, the
    result is ``mixed``; with no letters at all it is ``unknown``.
    """
    ru = 0
    en = 0
    for ch in text:
        if is_cyrillic(ch):
            ru += 1
        elif _is_latin(ch):
            en += 1

    total = ru + en
    if total == 0:  # no letters — digits/punct/whitespace/empty (нет букв)
        return LangResult(LANG_UNKNOWN, ru_ratio=0.0, en_ratio=0.0, confidence=0.0)

    ru_ratio = ru / total
    en_ratio = en / total

    if ru_ratio > DOMINANT_THRESHOLD:
        return LangResult(LANG_RU, ru_ratio, en_ratio, confidence=ru_ratio)
    if en_ratio > DOMINANT_THRESHOLD:
        return LangResult(LANG_EN, ru_ratio, en_ratio, confidence=en_ratio)

    # Neither script dominates, yet both are present → mixed. Confidence peaks at a
    # perfect 50/50 split and falls toward the 0.7 boundary (смесь).
    confidence = 2.0 * min(ru_ratio, en_ratio)
    return LangResult(LANG_MIXED, ru_ratio, en_ratio, confidence=confidence)
