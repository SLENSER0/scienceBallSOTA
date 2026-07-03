"""Agent preprocess node: language detection + text normalization (§13.7).

Implements Node 1 of the LangGraph QA workflow (§7.5 Node 1
``preprocess_question``): the very first step that cleans and characterizes a
raw RU/EN user question before intent classification (§13.8) and retrieval.

Responsibilities kept here (deliberately dependency-light — only ``re`` and
``unicodedata``; NO ``langdetect``/``pint``, so the node is fast and offline):

* **Язык / language** — detect ``ru`` | ``en`` | ``mixed`` from the
  Cyrillic-vs-Latin letter ratio (``unknown`` when there are no letters at all).
* **Нормализация / normalization** — collapse all Unicode whitespace (incl.
  ``NBSP`` U+00A0, narrow no-break space, …) to single ASCII spaces; fold fancy
  quotes (``“ ” « »`` → ``"``, ``‘ ’`` → ``'``) and en/em/figure dashes and the
  minus sign (``– — ― −`` → ``-``); the comparison operators ``≤`` / ``≥`` are
  **kept verbatim** because they carry numeric-constraint meaning (§7.5 unit
  parsing reads ``≤``/``≥`` bounds).
* **Дешёвые флаги / cheap intent flags** — keyword+digit heuristics matching how
  the domain queries read (§24.9 / :mod:`kg_extractors.query_parser`):
  ``is_comparison`` (RU ``сравни``/``сравнение``, ``vs``, ``против`` …),
  ``is_gap_intent`` (RU ``пробел``/``нет данных``/``не изучен`` …),
  ``has_numeric`` (a decimal digit is present, typically paired with a unit such
  as ``А/м²`` (current density), ``°C``, ``МПа``, ``ч``/``h``).

The heavy lifting (unit normalization via pint, canonical-vocabulary mapping,
numeric-constraint extraction) belongs to later nodes / the query parser; this
node only produces the cheap, deterministic signals that routing needs.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- character folding tables (§13.7 normalization) -------------------------
# Fancy quotes → straight ASCII quotes. Includes the Russian guillemets « »
# (кавычки-ёлочки) and low-9 quotes „ ‚ commonly produced by editors.
_QUOTE_MAP = {
    "“": '"',  # “ left double
    "”": '"',  # ” right double
    "„": '"',  # „ double low-9
    "‟": '"',  # ‟ double high-reversed-9
    "«": '"',  # « left guillemet
    "»": '"',  # » right guillemet
    "‘": "'",  # ‘ left single
    "’": "'",  # ’ right single
    "‚": "'",  # ‚ single low-9
    "‛": "'",  # ‛ single high-reversed-9
}
# Dashes / minus → ASCII hyphen-minus. ``≤``/``≥`` are intentionally absent.
_DASH_MAP = {
    "‒": "-",  # ‒ figure dash
    "–": "-",  # – en dash
    "—": "-",  # — em dash
    "―": "-",  # ― horizontal bar
    "−": "-",  # − minus sign
}
_CHAR_MAP = {**_QUOTE_MAP, **_DASH_MAP}

# --- intent keyword markers (RU/EN, lowercased substrings) ------------------
# Comparison / сравнение (§7.5 method_comparison; cf. query_parser _COMPARE_MARKERS).
_COMPARE_MARKERS: tuple[str, ...] = (
    "сравн",  # сравни / сравнить / сравнение / сравниваем
    "по сравнению",
    "против",
    " vs ",
    "vs.",
    " versus ",
    "compare",
    "comparison",
    " лучше ",
    " или ",
)
# Gap / пробел (§7.5 gap_analysis; cf. query_parser _GAP_MARKERS).
_GAP_MARKERS: tuple[str, ...] = (
    "пробел",  # пробелы / пробел в знаниях
    "нет данных",
    "нет эксперимент",
    "не изучен",
    "не исследов",
    "не хватает",
    "отсутству",
    "no data",
    "no experiment",
    "missing data",
    "gap",
)

_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN = re.compile(r"[a-z]", re.IGNORECASE)
_DIGIT = re.compile(r"\d")
_MULTISPACE = re.compile(r" {2,}")
# ``mixed`` requires both scripts to be *substantially* present, so a stray
# foreign letter (a chemical symbol, a loanword) does not flip the language.
_MIXED_RATIO = 0.35


@dataclass(frozen=True)
class PreprocessedQuery:
    """Result of the §13.7 preprocess node (§7.5 Node 1).

    Fields
    ------
    raw
        The original question exactly as received (сырой запрос).
    text
        Normalized query string: whitespace collapsed, fancy quotes/dashes
        folded, ``≤``/``≥`` preserved (нормализованный запрос).
    language
        ``ru`` | ``en`` | ``mixed`` | ``unknown`` (язык вопроса).
    is_comparison
        Cheap flag: the question compares alternatives (сравнение).
    is_gap_intent
        Cheap flag: the question asks about knowledge gaps (пробелы/нет данных).
    has_numeric
        Cheap flag: a decimal digit is present (обычно число с единицей, e.g.
        ``250 А/м²``).
    """

    raw: str
    text: str
    language: str
    is_comparison: bool
    is_gap_intent: bool
    has_numeric: bool

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields) for state/logging (§7.3)."""
        return {
            "raw": self.raw,
            "text": self.text,
            "language": self.language,
            "is_comparison": self.is_comparison,
            "is_gap_intent": self.is_gap_intent,
            "has_numeric": self.has_numeric,
        }


def _normalize(text: str) -> str:
    """Fold fancy punctuation and collapse Unicode whitespace (§13.7).

    Any character in Unicode category ``Zs`` (space separators — incl. NBSP
    U+00A0, narrow no-break space U+202F …) plus ASCII control whitespace is
    mapped to a single ASCII space; runs of spaces are collapsed and the result
    is stripped. ``≤``/``≥`` and digits/superscripts pass through untouched.
    """
    out: list[str] = []
    for ch in text:
        mapped = _CHAR_MAP.get(ch)
        if mapped is not None:
            out.append(mapped)
        elif ch in "\t\n\r\f\v" or unicodedata.category(ch) == "Zs":
            out.append(" ")
        else:
            out.append(ch)
    return _MULTISPACE.sub(" ", "".join(out)).strip()


def _detect_language(text: str) -> str:
    """Return ``ru`` | ``en`` | ``mixed`` | ``unknown`` (§13.7 язык).

    Uses the Cyrillic-vs-Latin letter ratio (cf. query_parser ``_detect_lang``);
    ``unknown`` when the text has no letters at all (e.g. empty or digits-only),
    so empty input degrades gracefully instead of defaulting to a real language.
    """
    cyr = len(_CYRILLIC.findall(text))
    lat = len(_LATIN.findall(text))
    if not cyr and not lat:
        return "unknown"
    if cyr and lat and min(cyr, lat) / max(cyr, lat) >= _MIXED_RATIO:
        return "mixed"
    return "ru" if cyr >= lat else "en"


def preprocess_query(text: str) -> PreprocessedQuery:
    """Preprocess a raw RU/EN question (§13.7 / §7.5 Node 1).

    Detects the language, normalizes whitespace + common Unicode punctuation,
    and derives the cheap ``is_comparison`` / ``is_gap_intent`` / ``has_numeric``
    flags. Empty / whitespace-only input is handled gracefully (empty ``text``,
    ``language='unknown'``, all flags ``False``).
    """
    raw = text or ""
    normalized = _normalize(raw)
    low = normalized.lower()
    return PreprocessedQuery(
        raw=raw,
        text=normalized,
        language=_detect_language(normalized),
        is_comparison=any(m in low for m in _COMPARE_MARKERS),
        is_gap_intent=any(m in low for m in _GAP_MARKERS),
        has_numeric=bool(_DIGIT.search(normalized)),
    )
