"""Chunk output contract — stable serialization boundary (§5.9).

The chunker (``ingestion_service.chunker``) packs source pages into
section-aware pieces; this module defines the *contract* those pieces cross
when they leave ingestion for the extractors: a frozen :class:`Chunk` with a
canonical field set, an :meth:`Chunk.as_dict` projection, a :meth:`Chunk.validate`
guard, and lossless JSONL round-trip helpers. Field names stay compatible with
the upstream ``Chunk`` (``text`` / ``chunk_type`` / ``page`` / ``char_start``)
so callers reading those keys are unaffected.

``chunk_type`` is drawn from :class:`ChunkType` (``prose`` / ``table_row`` /
``caption``). ``token_count`` is a whitespace/word count from
:func:`count_tokens` — a stdlib-only tokenizer that works on RU + EN text
(кириллица) with no heavy ML dependency.

Pure Python (``json``/``re``/``dataclasses`` only) so this boundary never
pulls in an LLM or optional ML stack.

Public API:

- :class:`ChunkType`     — the three accepted chunk kinds (str-enum);
- :class:`Chunk`         — frozen record with ``as_dict`` + ``validate``;
- :func:`count_tokens`   — whitespace/word token count (RU + EN);
- :func:`chunks_to_jsonl` / :func:`chunks_from_jsonl` — JSONL round-trip.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from enum import StrEnum

# --- tokenizer -----------------------------------------------------------------
#: A "word" token: a run of letters (Latin + Cyrillic + any Unicode alpha) or
#: digits. Punctuation and whitespace act only as separators and are not counted.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def count_tokens(text: str) -> int:
    """Return the whitespace/word token count of ``text`` (RU + EN).

    A simple stdlib-only tokenizer: tokens are maximal ``\\w+`` runs, so
    «медный купорос» → 2 and ``"Fe-18Cr-8Ni alloy"`` → 4 (``Fe`` ``18Cr`` ``8Ni``
    ``alloy``; the hyphens separate). Empty / whitespace-only text → 0.
    """
    if not text:
        return 0
    return len(_WORD_RE.findall(text))


# --- chunk kinds (§5.9) --------------------------------------------------------
class ChunkType(StrEnum):
    """The three accepted chunk kinds crossing the ingestion→extractor boundary.

    A :class:`~enum.StrEnum`, so a :class:`ChunkType` serializes as its bare
    value in JSON, stringifies to it (``str(ChunkType.PROSE) == "prose"``), and
    compares equal to the underlying string (``ChunkType.PROSE == "prose"``).
    """

    PROSE = "prose"
    TABLE_ROW = "table_row"
    CAPTION = "caption"


#: Fast membership test for validation / deserialization.
_VALID_TYPES: frozenset[str] = frozenset(t.value for t in ChunkType)


# --- chunk record (§5.9) -------------------------------------------------------
@dataclass(frozen=True)
class Chunk:
    """One chunk emitted by ingestion, ready to serialize (§5.9).

    Fields:

    - ``chunk_id``   — stable unique id for this chunk (provenance key);
    - ``doc_id``     — id of the source document the chunk came from;
    - ``text``       — the chunk body (verbatim source slice);
    - ``chunk_type`` — one of :class:`ChunkType` (``prose`` / ``table_row`` / ``caption``);
    - ``section``    — section path / heading the chunk sits under («» if none);
    - ``page``       — 1-based source page number (0 when unknown);
    - ``token_count``— whitespace/word token count of ``text`` (:func:`count_tokens`);
    - ``char_start`` / ``char_end`` — offsets of ``text`` within its source page.
    """

    chunk_id: str
    doc_id: str
    text: str
    chunk_type: str
    section: str
    page: int
    token_count: int
    char_start: int
    char_end: int

    def as_dict(self) -> dict[str, object]:
        """Return the canonical, JSON-ready projection of this chunk.

        ``chunk_type`` is emitted as its plain string value (never an ``Enum``
        repr) so the mapping is a pure ``str``/``int`` record.
        """
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "text": self.text,
            "chunk_type": str(self.chunk_type),
            "section": self.section,
            "page": self.page,
            "token_count": self.token_count,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    def validate(self) -> Chunk:
        """Assert the chunk is well-formed; return ``self`` for chaining.

        Rejects (``ValueError``): empty/whitespace-only ``text``; an unknown
        ``chunk_type``; a negative ``token_count``; and negative or reversed
        offsets (``char_start`` < 0, ``char_end`` < 0, or ``char_end`` <
        ``char_start``).
        """
        if not self.text or not self.text.strip():
            raise ValueError("chunk text must be non-empty")
        if str(self.chunk_type) not in _VALID_TYPES:
            raise ValueError(f"unknown chunk_type: {self.chunk_type!r}")
        if self.token_count < 0:
            raise ValueError(f"token_count must be >= 0, got {self.token_count}")
        if self.char_start < 0:
            raise ValueError(f"char_start must be >= 0, got {self.char_start}")
        if self.char_end < 0:
            raise ValueError(f"char_end must be >= 0, got {self.char_end}")
        if self.char_end < self.char_start:
            raise ValueError(
                f"char_end ({self.char_end}) must be >= char_start ({self.char_start})"
            )
        return self


#: Field names in declaration order — the canonical JSONL key set.
_FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in fields(Chunk))


def _chunk_from_dict(data: dict[str, object]) -> Chunk:
    """Build a :class:`Chunk` from a decoded mapping (missing keys → ``KeyError``)."""
    return Chunk(
        chunk_id=str(data["chunk_id"]),
        doc_id=str(data["doc_id"]),
        text=str(data["text"]),
        chunk_type=str(data["chunk_type"]),
        section=str(data["section"]),
        page=int(data["page"]),  # type: ignore[arg-type]
        token_count=int(data["token_count"]),  # type: ignore[arg-type]
        char_start=int(data["char_start"]),  # type: ignore[arg-type]
        char_end=int(data["char_end"]),  # type: ignore[arg-type]
    )


def chunks_to_jsonl(chunks: list[Chunk]) -> str:
    """Serialize chunks to JSONL — one JSON object per line (§5.9).

    An empty list yields the empty string (no trailing newline). Otherwise each
    line is ``chunk.as_dict()`` with ``ensure_ascii=False`` so RU text stays
    human-readable, and lines are newline-joined without a trailing newline.
    """
    return "\n".join(json.dumps(c.as_dict(), ensure_ascii=False) for c in chunks)


def chunks_from_jsonl(s: str) -> list[Chunk]:
    """Parse JSONL back into chunks — inverse of :func:`chunks_to_jsonl` (§5.9).

    Blank lines are skipped, so round-tripping is lossless regardless of a
    trailing newline. An empty / whitespace-only string yields ``[]``.
    """
    out: list[Chunk] = []
    for line in s.splitlines():
        if not line.strip():
            continue
        out.append(_chunk_from_dict(json.loads(line)))
    return out
