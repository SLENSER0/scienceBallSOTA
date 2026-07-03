"""Intra/inter-document chunk de-duplication — collapse identical text (§5.9).

A chunked corpus routinely carries the *same* text twice: a table caption
repeated on every page, a boiler-plate legend copied across documents, the same
paragraph OCR'd from two scans. Feeding both copies to the extractors wastes the
token budget and double-counts evidence. This module folds chunks whose text is
*identical after normalization* into a single group, keeps the first occurrence
(input order), and drops the rest — so downstream sees each distinct text once.

Normalization (:func:`normalize_chunk_text`) is deliberately blunt: lowercase,
collapse every run of whitespace to one space, and strip leading/trailing
punctuation-only noise, so ``'Table 1.'`` and ``'table 1'`` land on the same
key while genuinely different texts never collide.

Grouping (:func:`dedup_chunks`) walks the batch once, in input order. Chunks
sharing a normalized key join one group; the FIRST chunk_id seen for that key is
*kept*, every later member is *dropped*. Distinct texts never merge, singletons
form one-member groups, and ``kept ∪ dropped`` is exactly the input ids.

Pure Python — stdlib only, no LLM, no I/O, order-preserving and hand-checkable.

Public API:

- :class:`DedupResult`        — frozen ``kept`` / ``dropped`` / ``groups`` with
  :meth:`DedupResult.as_dict`;
- :func:`normalize_chunk_text` — canonical key for a chunk's text;
- :func:`dedup_chunks`         — fold ``[{chunk_id, text}, …]`` into groups.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WHITESPACE_RE = re.compile(r"\s+")


def _is_noise_char(ch: str) -> bool:
    """True for a punctuation / symbol char that carries no content (шум)."""
    category = unicodedata.category(ch)
    # P* = punctuation, S* = symbols — strip these when they wrap the text.
    return category.startswith("P") or category.startswith("S")


@dataclass(frozen=True)
class DedupResult:
    """Outcome of chunk de-duplication (§5.9).

    Fields
    ------
    kept
        Chunk ids that survive, one per distinct normalized text, in first-seen
        order (оставленные — по первому вхождению).
    dropped
        Chunk ids collapsed into an earlier keeper, in input order
        (отброшенные дубли).
    groups
        One tuple per distinct text, each holding every member chunk_id
        (singletons included) in input order; the group's first id is its
        keeper (группы: первый id — оставленный).
    """

    kept: tuple[str, ...]
    dropped: tuple[str, ...]
    groups: tuple[tuple[str, ...], ...]

    def as_dict(self) -> dict[str, object]:
        """Full structured view (JSON-friendly; ``groups`` as a list of lists)."""
        return {
            "kept": list(self.kept),
            "dropped": list(self.dropped),
            "groups": [list(group) for group in self.groups],
        }


def normalize_chunk_text(text: str) -> str:
    """Canonical key for a chunk's text (§5.9).

    Lowercases, collapses every run of whitespace to a single space, and strips
    leading/trailing punctuation-or-symbol-only noise. Interior punctuation is
    preserved. Examples: ``'Table 1.'`` and ``'table 1'`` both map to
    ``'table 1'``; ``normalize_chunk_text('  Al   Cu.  ') == 'al cu'``. A string
    that is empty or all-whitespace/punctuation normalizes to ``''``.
    """
    collapsed = _WHITESPACE_RE.sub(" ", text).strip().lower()
    start = 0
    end = len(collapsed)
    while start < end and _is_noise_char(collapsed[start]):
        start += 1
    while end > start and _is_noise_char(collapsed[end - 1]):
        end -= 1
    return collapsed[start:end].strip()


def dedup_chunks(chunks: list[dict]) -> DedupResult:
    """Fold chunks with identical normalized text into groups (§5.9).

    Each chunk is a dict with keys ``chunk_id: str`` and ``text: str``. Walks the
    batch once, in input order: chunks sharing a :func:`normalize_chunk_text`
    key join one group, the FIRST chunk_id for that key is *kept*, later members
    are *dropped*. Distinct texts never merge; every chunk (even a unique one)
    belongs to exactly one group, so ``kept ∪ dropped`` equals the input ids and
    ``dropped`` is exactly the inputs minus ``kept``. Empty input yields empty
    ``kept`` / ``dropped`` and no groups.
    """
    key_to_index: dict[str, int] = {}
    groups: list[list[str]] = []
    kept: list[str] = []
    dropped: list[str] = []
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        key = normalize_chunk_text(chunk["text"])
        if key in key_to_index:
            groups[key_to_index[key]].append(chunk_id)
            dropped.append(chunk_id)
        else:
            key_to_index[key] = len(groups)
            groups.append([chunk_id])
            kept.append(chunk_id)
    return DedupResult(
        kept=tuple(kept),
        dropped=tuple(dropped),
        groups=tuple(tuple(group) for group in groups),
    )
