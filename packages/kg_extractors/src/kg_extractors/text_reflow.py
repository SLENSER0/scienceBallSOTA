"""§5.7/§5.11 parse cleanup before chunking — de-hyphenation & soft-wrap reflow.

Очистка текста перед чанкованием: склейка перенесённых слов и мягких переносов строк.

PDF/OCR text layers routinely split a single word across a line boundary with a trailing
hyphen (``micro-\\nstructure``) and hard-wrap running prose into many short physical lines.
Both artefacts corrupt downstream chunking, span offsets and entity matching. This module
undoes them with pure ``re`` (Unicode-aware, so RU Cyrillic joins work) — no dependency:

    «micro-\\nstructure»  -> «microstructure»   (de-hyphenate: drop hyphen + newline)
    «a\\nb»               -> «a b»              (soft wrap: single newline -> space)
    «a\\n\\nb»            -> «a\\n\\nb»          (paragraph break: blank line preserved)

De-hyphenation only fires on a hyphen immediately followed by a newline (``-\\n``); a genuine
hyphenated compound such as ``state-of-the-art`` — hyphen followed by a letter or a space,
never a newline — is left untouched. Soft-wrap collapsing folds a *single* intra-paragraph
newline to one space while any run of two or more newlines (a blank-line paragraph break) is
kept verbatim.

Public API:

- :class:`ReflowResult` — frozen result (cleaned text + join counts) with :meth:`as_dict`.
- :func:`dehyphenate` — surface -> ``(joined_text, n_dehyphenated)``.
- :func:`join_soft_wraps` — surface -> ``(collapsed_text, n_joins)``.
- :func:`reflow` — run both, in order, and report both counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["ReflowResult", "dehyphenate", "join_soft_wraps", "reflow"]

# Word char, trailing hyphen, newline (+ any leading indent on the wrapped line), word char.
# Unicode ``\w`` matches Cyrillic, so «струк-\nтура» folds just like «micro-\nstructure».
_DEHYPHEN_RE = re.compile(r"(\w)-\n[ \t]*(\w)")

# A lone newline that is neither preceded nor followed by another newline — i.e. NOT part of a
# blank-line paragraph break. Such a newline is a hard soft-wrap and collapses to one space.
_SOFT_WRAP_RE = re.compile(r"(?<!\n)\n(?!\n)")


@dataclass(frozen=True)
class ReflowResult:
    """Результат очистки текста / cleaned text plus how many joins were applied.

    Attributes:
        text: The reflowed text after de-hyphenation and soft-wrap collapsing.
        n_dehyphenated: Count of line-break hyphenations undone.
        n_joins: Count of single intra-paragraph newlines collapsed to spaces.
    """

    text: str
    n_dehyphenated: int
    n_joins: int

    def as_dict(self) -> dict:
        """Return a plain ``dict`` view / словарное представление результата."""
        return {
            "text": self.text,
            "n_dehyphenated": self.n_dehyphenated,
            "n_joins": self.n_joins,
        }


def dehyphenate(text: str) -> tuple[str, int]:
    """Join words split by a trailing hyphen across a newline / склейка переносов.

    ``micro-\\nstructure`` -> ``microstructure``. Only a hyphen immediately followed by a
    newline is joined; a genuine compound (``state-of-the-art``) has no ``-\\n`` and is kept.

    Args:
        text: Raw text possibly containing line-break hyphenations.

    Returns:
        Tuple of ``(joined_text, n_dehyphenated)``.
    """
    count = 0

    def _join(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(1) + match.group(2)

    return _DEHYPHEN_RE.sub(_join, text), count


def join_soft_wraps(text: str) -> tuple[str, int]:
    """Collapse single intra-paragraph newlines to spaces / склейка мягких переносов.

    ``a\\nb`` -> ``a b``. A run of two or more newlines is a paragraph break and is preserved
    verbatim (``a\\n\\nb`` stays ``a\\n\\nb``).

    Args:
        text: Text with hard-wrapped physical lines.

    Returns:
        Tuple of ``(collapsed_text, n_joins)``.
    """
    count = 0

    def _space(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return " "

    return _SOFT_WRAP_RE.sub(_space, text), count


def reflow(text: str) -> ReflowResult:
    """Run de-hyphenation then soft-wrap collapsing / полная очистка текста.

    Args:
        text: Raw parsed text.

    Returns:
        A frozen :class:`ReflowResult` carrying the cleaned text and both join counts.
    """
    dehyphenated, n_dehyphenated = dehyphenate(text)
    joined, n_joins = join_soft_wraps(dehyphenated)
    return ReflowResult(text=joined, n_dehyphenated=n_dehyphenated, n_joins=n_joins)
