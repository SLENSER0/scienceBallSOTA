"""Text-quality gate for evidence provenance (RAG grounding hardening).

Retrieval over an OCR'd corpus surfaces two kinds of unusable «evidence»: raw
PDF-extraction artifacts — ``(cid:20)`` glyph fallbacks, dotted table-of-contents
leaders, words shattered into spaced single glyphs — and near-empty fragments.
Citing such spans as sources, or feeding them to the synthesis LLM as FACTS,
pollutes the answer and inflates the citation count with noise (the benchmark saw
~35 % of citations were junk of this kind).

These pure, dependency-free predicates flag such text so the answer path can drop
it from citations and from the LLM context, and measure how much of the retrieved
support is actually readable (:func:`clean_fraction`) — a signal that feeds
confidence calibration. The gate is deliberately *conservative*: it fires only on
a clear junk signal, so legitimate evidence is never silently dropped.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# A PDF glyph-fallback artifact: the extractor could not map a glyph and emitted
# its raw character id, e.g. «(cid:20)». A dead giveaway of unusable OCR text.
_CID_RE = re.compile(r"\(cid:\s*\d+\s*\)")

# 6+ dotted leaders — a table-of-contents / index row («. . . . . .»), not prose.
_DOTTED_LEADER_RE = re.compile(r"(?:\.\s?){6,}")

# 5+ consecutive one/two-letter tokens — OCR shattered a word into spaced glyphs
# («о б р а з» / «при мно гок ратн ом»). Cyrillic + Latin, incl. ё/Ё.
_SHATTERED_RE = re.compile(r"(?:(?:^|\s)[A-Za-zА-Яа-яЁё]{1,2}(?=\s)){5,}")

# Below this many characters a span is a fragment, not citable evidence prose.
MIN_LEN = 12


def is_clean_text(text: str | None) -> bool:
    """True if ``text`` reads as usable evidence prose (not an OCR/extraction artifact).

    Conservative by design — only a *clear* junk signal rejects a span:
    ``(cid:NN)`` glyph fallbacks, dotted TOC leaders, shattered word-spacing, a
    too-short fragment, low letter density, or a ballooned space ratio (broken
    tokenisation). Empty / whitespace-only text is never clean.
    """
    if not text:
        return False
    t = text.strip()
    if len(t) < MIN_LEN:
        return False
    if _CID_RE.search(t):
        return False
    if _DOTTED_LEADER_RE.search(t):
        return False
    if _SHATTERED_RE.search(t):
        return False
    # Letter density: real prose is mostly letters + spaces; a low ratio means the
    # span is mostly symbols / digits / punctuation noise.
    letters = sum(ch.isalpha() for ch in t)
    if letters / len(t) < 0.5:
        return False
    # Broken word-spacing: OCR that splits words balloons the space ratio well past
    # normal prose (~0.14–0.18 for RU/EN). 0.34 is a wide, safe margin.
    if t.count(" ") / len(t) > 0.34:
        return False
    # Shattered tokens: OCR that fragments words leaves many tiny «tokens»
    # («при мно гок ратн ом …»). Real prose averages ~5-6 chars/word; a mean token
    # length under 3 over enough tokens is a reliable shatter signal.
    tokens = t.split()
    return not (len(tokens) >= 6 and sum(len(w) for w in tokens) / len(tokens) < 3.0)


def clean_fraction(texts: Iterable[str | None]) -> float:
    """Fraction of ``texts`` passing :func:`is_clean_text` (0.0 for an empty input)."""
    items = list(texts)
    if not items:
        return 0.0
    return sum(1 for t in items if is_clean_text(t)) / len(items)
