"""Chunk linkage — NEXT_CHUNK edges + section membership (§5.10).

The chunker emits a flat sequence of :class:`~kg_extractors.chunk_contract.Chunk`
records (see §5.9). This module turns that sequence into the *link* layer the
graph needs: an ordered chain of ``NEXT_CHUNK`` edges (document order) plus
``same_section`` edges tying together the chunks that belong to one section
(секционная принадлежность). Every edge is a frozen :class:`ChunkLink`
referencing chunks by their ``chunk_id`` — the same provenance key the contract
serializes — so this layer never copies chunk bodies.

Two relation kinds cross this boundary:

- ``next`` (:data:`REL_NEXT`)  — consecutive chunks in document order,
  ``chunks[i] → chunks[i + 1]``; the reading-order backbone.
- ``same_section`` (:data:`REL_SAME_SECTION`) — each chunk is tied to the
  previous chunk carrying the *same* non-empty ``section`` value, so a section's
  chunks form an ordered chain even when other sections interleave them. A
  change of section value simply starts a new chain (no cross-section edge).

Pure Python (``dataclasses`` only): building on the read-only
:mod:`kg_extractors.chunk_contract` shape, this boundary never pulls in an LLM
or the optional ML stack.

Kuzu note: when these links land in the graph the custom edge props are *not*
queryable columns — a query must ``RETURN`` the base columns and read the rest
via ``get_node`` / ``get_rel``; nothing here depends on that, it stays pure data.

Public API:

- :class:`ChunkLink`      — frozen ``{from_chunk, to_chunk, rel}`` with ``as_dict``;
- :data:`REL_NEXT` / :data:`REL_SAME_SECTION` — the two relation kinds;
- :func:`link_chunks`     — build the ``next`` + ``same_section`` edge list;
- :func:`chunk_neighbors` — the ``{prev, next}`` document-order neighbours of a chunk.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from kg_extractors.chunk_contract import Chunk

# --- relation kinds (§5.10) ----------------------------------------------------
#: Reading-order backbone: ``chunks[i] → chunks[i + 1]`` in document order.
REL_NEXT = "next"
#: Section membership: a chunk tied to the previous chunk of the same section.
REL_SAME_SECTION = "same_section"

#: The relation kinds a :class:`ChunkLink` may carry (fast membership test).
VALID_RELS: frozenset[str] = frozenset({REL_NEXT, REL_SAME_SECTION})


# --- link record (§5.10) -------------------------------------------------------
@dataclass(frozen=True)
class ChunkLink:
    """One directed edge between two chunks, referenced by ``chunk_id`` (§5.10).

    Fields:

    - ``from_chunk`` — ``chunk_id`` of the source (earlier) chunk;
    - ``to_chunk``   — ``chunk_id`` of the target (later) chunk;
    - ``rel``        — the relation kind, one of :data:`REL_NEXT` /
      :data:`REL_SAME_SECTION` (``next`` / ``same_section``).

    Both endpoints of every edge run in document order, so ``from_chunk`` always
    precedes ``to_chunk`` in the source sequence (направленное ребро вперёд).
    """

    from_chunk: str
    to_chunk: str
    rel: str

    def as_dict(self) -> dict[str, str]:
        """Return the canonical, JSON-ready projection of this link.

        ``rel`` is emitted as its plain string value so the mapping is a pure
        ``str`` record (три строковых поля).
        """
        return {
            "from_chunk": self.from_chunk,
            "to_chunk": self.to_chunk,
            "rel": self.rel,
        }

    def validate(self) -> ChunkLink:
        """Assert the link is well-formed; return ``self`` for chaining.

        Rejects (``ValueError``): an empty ``from_chunk`` / ``to_chunk`` id, a
        self-loop (``from_chunk == to_chunk``), or an unknown ``rel`` outside
        :data:`VALID_RELS`.
        """
        if not self.from_chunk:
            raise ValueError("from_chunk must be a non-empty chunk_id")
        if not self.to_chunk:
            raise ValueError("to_chunk must be a non-empty chunk_id")
        if self.from_chunk == self.to_chunk:
            raise ValueError(f"link must not be a self-loop: {self.from_chunk!r}")
        if self.rel not in VALID_RELS:
            raise ValueError(f"unknown rel: {self.rel!r}")
        return self


def _has_section(section: str) -> bool:
    """``True`` when *section* is a real heading (not empty / whitespace-only)."""
    return bool(section) and bool(section.strip())


def link_chunks(chunks: Sequence[Chunk]) -> list[ChunkLink]:
    """Build the ``next`` + ``same_section`` edge list for a chunk sequence (§5.10).

    The result is deterministic and ordered: first every ``NEXT_CHUNK`` edge in
    document order (``chunks[i] → chunks[i + 1]``), then every ``same_section``
    edge — each chunk tied to the previous chunk carrying the *same* non-empty
    ``section`` value, so one section's chunks form an ordered chain even when
    other sections interleave them (a section change just starts a new chain).

    Chunks with an empty / whitespace-only ``section`` take part in the ``next``
    chain but never receive a ``same_section`` edge (нечего разделять). A list of
    fewer than two chunks yields no edges at all.
    """
    links: list[ChunkLink] = []

    # NEXT_CHUNK backbone — consecutive pairs in document order.
    for prev, cur in pairwise(chunks):
        links.append(ChunkLink(prev.chunk_id, cur.chunk_id, REL_NEXT))

    # same_section chains — link each chunk to the last chunk of its section.
    last_in_section: dict[str, str] = {}
    for chunk in chunks:
        section = chunk.section
        if not _has_section(section):
            continue
        prev_id = last_in_section.get(section)
        if prev_id is not None:
            links.append(ChunkLink(prev_id, chunk.chunk_id, REL_SAME_SECTION))
        last_in_section[section] = chunk.chunk_id

    return links


def chunk_neighbors(chunks: Sequence[Chunk], chunk_id: str) -> dict[str, str | None]:
    """Return the document-order neighbours of ``chunk_id`` as ``{prev, next}`` (§5.10).

    ``prev`` / ``next`` hold the ``chunk_id`` of the chunk immediately before /
    after the target in the source sequence, or ``None`` at an end (соседи по
    порядку чтения): the first chunk has ``prev is None`` and the last chunk has
    ``next is None``. The first occurrence of ``chunk_id`` is used.

    Raises ``ValueError`` when ``chunk_id`` is not present in *chunks*.
    """
    index: int | None = None
    for i, chunk in enumerate(chunks):
        if chunk.chunk_id == chunk_id:
            index = i
            break
    if index is None:
        raise ValueError(f"chunk_id not found: {chunk_id!r}")

    prev_id = chunks[index - 1].chunk_id if index > 0 else None
    next_id = chunks[index + 1].chunk_id if index < len(chunks) - 1 else None
    return {"prev": prev_id, "next": next_id}
