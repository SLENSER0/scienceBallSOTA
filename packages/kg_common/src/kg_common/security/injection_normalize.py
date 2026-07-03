"""Unicode obfuscation normalizer for the injection guardrail (§19.6).

The pattern-based scanner in :mod:`injection_scan` matches phrases like
``ignore previous instructions`` with plain regexes. An attacker can defeat those
regexes by splitting words with **zero-width** code points or by swapping ASCII
letters for visually identical **homoglyphs** (Cyrillic ``а/е/о/с/р/і`` or
fullwidth ``Ａ``). This pre-scan folds such text back to plain ASCII *before* it
reaches the scanner, so obfuscated payloads still hit the signatures.

Нормализатор чисто-функциональный: убирает нулевой ширины символы, отображает
таблицу «двойников» (homoglyphs) в ASCII и никогда не мутирует вход.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Zero-width / invisible joiners used to split words inside a payload.
# U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ, U+2060 WORD JOINER, U+FEFF BOM.
_ZERO_WIDTH: frozenset[str] = frozenset("​‌‍⁠﻿")

# Fixed confusable table: homoglyph → ASCII. Cyrillic look-alikes first, then the
# fullwidth ASCII block (U+FF01–U+FF5E maps onto U+0021–U+007E by a 0xFEE0 offset).
_HOMOGLYPHS: dict[str, str] = {
    # Cyrillic lower-case look-alikes.
    "а": "a",  # U+0430
    "е": "e",  # U+0435
    "о": "o",  # U+043E
    "с": "c",  # U+0441
    "р": "p",  # U+0440
    "і": "i",  # U+0456
    # Cyrillic upper-case look-alikes.
    "А": "A",  # U+0410
    "Е": "E",  # U+0415
    "О": "O",  # U+041E
    "С": "C",  # U+0421
    "Р": "P",  # U+0420
    "І": "I",  # U+0406
}
# Extend with the fullwidth ASCII block Ａ..Ｚ, ａ..ｚ, ０..９ and punctuation.
_HOMOGLYPHS.update({chr(cp): chr(cp - 0xFEE0) for cp in range(0xFF01, 0xFF5F)})


@dataclass(frozen=True)
class NormalizeResult:
    """Result of normalizing untrusted text («результат нормализации»)."""

    text: str
    removed_zero_width: int
    homoglyphs_mapped: int
    changed: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict (roundtrips via ``NormalizeResult(**d)``)."""
        return {
            "text": self.text,
            "removed_zero_width": self.removed_zero_width,
            "homoglyphs_mapped": self.homoglyphs_mapped,
            "changed": self.changed,
        }


def strip_zero_width(s: str) -> str:
    """Return *s* with every zero-width / invisible code point removed.

    Убирает U+200B–U+200D, U+2060 и U+FEFF; вход не мутируется.
    """
    if not any(ch in _ZERO_WIDTH for ch in s):
        return s
    return "".join(ch for ch in s if ch not in _ZERO_WIDTH)


def map_homoglyphs(s: str) -> str:
    """Return *s* with each known homoglyph folded to its ASCII counterpart.

    Отображает фиксированную таблицу «двойников» (Cyrillic, fullwidth) в ASCII.
    """
    if not any(ch in _HOMOGLYPHS for ch in s):
        return s
    return "".join(_HOMOGLYPHS.get(ch, ch) for ch in s)


def normalize_text(s: str) -> NormalizeResult:
    """Strip zero-width chars then fold homoglyphs, reporting counts (§19.6).

    Возвращает :class:`NormalizeResult` с числом удалённых нулевой ширины символов
    и заменённых «двойников»; ``changed`` истинно тогда и только тогда, когда
    итоговый текст отличается от входного.
    """
    removed_zero_width = sum(1 for ch in s if ch in _ZERO_WIDTH)
    homoglyphs_mapped = sum(1 for ch in s if ch in _HOMOGLYPHS)
    text = map_homoglyphs(strip_zero_width(s))
    return NormalizeResult(
        text=text,
        removed_zero_width=removed_zero_width,
        homoglyphs_mapped=homoglyphs_mapped,
        changed=text != s,
    )
