"""Chunk-corpus statistics — one glance at a chunked document set (§5.14).

Given the chunks the chunker emits (:class:`~kg_extractors.chunk_contract.Chunk`,
§5.9), fold the whole batch into a single frozen :class:`ChunkStats`: how many
chunks there are, the token budget they carry, and how they distribute across
chunk *kinds* and *source documents*. Curators use this to spot a corpus that is
lopsided (one document dominating), starved (near-empty chunks), or mistyped
(all ``prose``, no ``table_row``) before it is fed to the extractors.

Statistics collected:

* ``n``            — number of chunks in the batch (всего чанков);
* ``total_tokens`` — sum of every chunk's ``token_count`` (сумма токенов);
* ``avg_tokens``   — mean tokens per chunk, rounded to 2 dp; ``0.0`` when empty
  (среднее токенов на чанк);
* ``by_type``      — ``chunk_type → count`` histogram in first-seen order
  (гистограмма по типу);
* ``by_doc``       — ``doc_id → count`` histogram in first-seen order
  (гистограмма по документу);
* ``empty``        — ids of chunks whose ``text`` is empty / whitespace-only, in
  input order (пустые чанки).

Insertion order is preserved everywhere, so the histograms and the ``empty``
list are stable and hand-checkable. Pure Python — stdlib only, no LLM, no I/O.

Public API:

- :class:`ChunkStats` — frozen summary with :meth:`ChunkStats.as_dict`;
- :func:`chunk_stats` — fold a chunk iterable into a :class:`ChunkStats`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from kg_extractors.chunk_contract import Chunk


@dataclass(frozen=True)
class ChunkStats:
    """Corpus-level statistics over a batch of chunks (§5.14).

    Fields
    ------
    n
        Number of chunks in the batch (всего чанков).
    total_tokens
        Sum of every chunk's ``token_count`` (сумма токенов).
    avg_tokens
        Mean tokens per chunk (``total_tokens / n``) rounded to 2 decimal
        places; ``0.0`` for an empty batch (среднее токенов на чанк).
    by_type
        ``chunk_type → count`` histogram in first-seen order (по типу).
    by_doc
        ``doc_id → count`` histogram in first-seen order (по документу).
    empty
        Ids of chunks with empty / whitespace-only ``text``, in input order
        (пустые чанки); ``len(empty)`` is how many are flagged.
    """

    n: int
    total_tokens: int
    avg_tokens: float
    by_type: dict[str, int] = field(default_factory=dict)
    by_doc: dict[str, int] = field(default_factory=dict)
    empty: list[str] = field(default_factory=list)

    @property
    def has_empty(self) -> bool:
        """True when at least one chunk was flagged as empty / whitespace-only."""
        return len(self.empty) > 0

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, JSON-friendly, deep-copied)."""
        return {
            "n": self.n,
            "total_tokens": self.total_tokens,
            "avg_tokens": self.avg_tokens,
            "by_type": dict(self.by_type),
            "by_doc": dict(self.by_doc),
            "empty": list(self.empty),
        }


def chunk_stats(chunks: Iterable[Chunk]) -> ChunkStats:
    """Fold a chunk iterable into a :class:`ChunkStats` summary (§5.14).

    Walks the batch once, in input order: counts chunks, sums ``token_count``,
    builds the ``by_type`` / ``by_doc`` histograms (first-seen key order), and
    flags every chunk whose ``text`` is empty or whitespace-only. ``avg_tokens``
    is the mean rounded to 2 dp. An empty input yields an all-zero summary
    (``n == total_tokens == 0``, ``avg_tokens == 0.0``, empty collections).
    """
    n = 0
    total_tokens = 0
    by_type: dict[str, int] = {}
    by_doc: dict[str, int] = {}
    empty: list[str] = []
    for chunk in chunks:
        n += 1
        total_tokens += chunk.token_count
        chunk_type = str(chunk.chunk_type)
        by_type[chunk_type] = by_type.get(chunk_type, 0) + 1
        by_doc[chunk.doc_id] = by_doc.get(chunk.doc_id, 0) + 1
        if not chunk.text or not chunk.text.strip():
            empty.append(chunk.chunk_id)
    avg_tokens = round(total_tokens / n, 2) if n else 0.0
    return ChunkStats(
        n=n,
        total_tokens=total_tokens,
        avg_tokens=avg_tokens,
        by_type=by_type,
        by_doc=by_doc,
        empty=empty,
    )
