"""Chunk-linkage tests — NEXT_CHUNK edges + section membership (§5.10).

Hand-checked expectations over small chunk sequences (RU + EN sections): a
sequential ``next`` chain in document order, ``same_section`` chains grouping a
section's chunks, a section change starting a fresh chain, document-order
``{prev, next}`` neighbours (including the no-prev / no-next ends), degenerate
single / empty inputs, and the exact ``as_dict`` shape.
"""

from __future__ import annotations

import pytest

from kg_extractors.chunk_contract import Chunk, ChunkType
from kg_extractors.chunk_linker import (
    REL_NEXT,
    REL_SAME_SECTION,
    ChunkLink,
    chunk_neighbors,
    link_chunks,
)


def _mk(chunk_id: str, section: str, *, page: int = 1) -> Chunk:
    """Build a minimal valid prose chunk (only id / section vary per test)."""
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc1",
        text="Образец Fe-18Cr отжигали при 1050 C.",
        chunk_type=ChunkType.PROSE.value,
        section=section,
        page=page,
        token_count=6,
        char_start=0,
        char_end=36,
    )


def _rels(links: list[ChunkLink], rel: str) -> list[tuple[str, str]]:
    """Return ``(from, to)`` pairs for every link of kind *rel*, in order."""
    return [(link.from_chunk, link.to_chunk) for link in links if link.rel == rel]


def test_sequential_next_links_for_three_chunks() -> None:
    chunks = [_mk("d:0", "Results"), _mk("d:1", "Results"), _mk("d:2", "Results")]
    links = link_chunks(chunks)
    # 3 chunks → exactly 2 NEXT edges: d:0→d:1 and d:1→d:2.
    assert _rels(links, REL_NEXT) == [("d:0", "d:1"), ("d:1", "d:2")]
    assert all(link.rel in {REL_NEXT, REL_SAME_SECTION} for link in links)


def test_same_section_links_group() -> None:
    chunks = [_mk("d:0", "Methods"), _mk("d:1", "Methods"), _mk("d:2", "Methods")]
    links = link_chunks(chunks)
    # The three same-section chunks form one chain: d:0→d:1→d:2.
    assert _rels(links, REL_SAME_SECTION) == [("d:0", "d:1"), ("d:1", "d:2")]


def test_neighbors_prev_next_correct() -> None:
    chunks = [_mk("d:0", "S"), _mk("d:1", "S"), _mk("d:2", "S")]
    assert chunk_neighbors(chunks, "d:1") == {"prev": "d:0", "next": "d:2"}


def test_first_chunk_has_no_prev() -> None:
    chunks = [_mk("d:0", "S"), _mk("d:1", "S"), _mk("d:2", "S")]
    assert chunk_neighbors(chunks, "d:0") == {"prev": None, "next": "d:1"}


def test_last_chunk_has_no_next() -> None:
    chunks = [_mk("d:0", "S"), _mk("d:1", "S"), _mk("d:2", "S")]
    assert chunk_neighbors(chunks, "d:2") == {"prev": "d:1", "next": None}


def test_single_chunk_yields_no_links() -> None:
    links = link_chunks([_mk("d:0", "Results")])
    assert links == []
    # A lone chunk has neither neighbour.
    assert chunk_neighbors([_mk("d:0", "Results")], "d:0") == {"prev": None, "next": None}


def test_section_change_breaks_same_section() -> None:
    # d:0/d:1 in «Введение», d:2/d:3 in «Результаты».
    chunks = [
        _mk("d:0", "Введение"),
        _mk("d:1", "Введение"),
        _mk("d:2", "Результаты"),
        _mk("d:3", "Результаты"),
    ]
    links = link_chunks(chunks)
    # NEXT chain spans the whole document regardless of section.
    assert _rels(links, REL_NEXT) == [("d:0", "d:1"), ("d:1", "d:2"), ("d:2", "d:3")]
    # same_section stays within a section: no d:1→d:2 edge across the boundary.
    assert _rels(links, REL_SAME_SECTION) == [("d:0", "d:1"), ("d:2", "d:3")]


def test_link_as_dict_shape() -> None:
    chunks = [_mk("d:0", "Results"), _mk("d:1", "Results")]
    links = link_chunks(chunks)
    next_link = next(link for link in links if link.rel == REL_NEXT)
    assert next_link.as_dict() == {"from_chunk": "d:0", "to_chunk": "d:1", "rel": "next"}
    same = next(link for link in links if link.rel == REL_SAME_SECTION)
    assert same.as_dict() == {
        "from_chunk": "d:0",
        "to_chunk": "d:1",
        "rel": "same_section",
    }
    assert set(next_link.as_dict()) == {"from_chunk", "to_chunk", "rel"}


def test_empty_input_yields_no_links() -> None:
    assert link_chunks([]) == []


def test_empty_section_gets_no_same_section() -> None:
    # Empty / whitespace-only sections join the NEXT chain but share nothing.
    chunks = [_mk("d:0", ""), _mk("d:1", "   "), _mk("d:2", "")]
    links = link_chunks(chunks)
    assert _rels(links, REL_NEXT) == [("d:0", "d:1"), ("d:1", "d:2")]
    assert _rels(links, REL_SAME_SECTION) == []


def test_non_contiguous_same_section_chains_across_gap() -> None:
    # «Results» reappears after a «Methods» chunk → the two Results chunks chain.
    chunks = [_mk("d:0", "Results"), _mk("d:1", "Methods"), _mk("d:2", "Results")]
    links = link_chunks(chunks)
    assert _rels(links, REL_SAME_SECTION) == [("d:0", "d:2")]
    assert _rels(links, REL_NEXT) == [("d:0", "d:1"), ("d:1", "d:2")]


def test_neighbors_unknown_id_raises() -> None:
    chunks = [_mk("d:0", "S"), _mk("d:1", "S")]
    with pytest.raises(ValueError, match="chunk_id not found"):
        chunk_neighbors(chunks, "d:99")


def test_link_validate_rejects_self_loop_and_bad_rel() -> None:
    with pytest.raises(ValueError, match="self-loop"):
        ChunkLink("d:0", "d:0", REL_NEXT).validate()
    with pytest.raises(ValueError, match="unknown rel"):
        ChunkLink("d:0", "d:1", "sibling").validate()
    # A well-formed link validates and returns itself for chaining.
    good = ChunkLink("d:0", "d:1", REL_SAME_SECTION)
    assert good.validate() is good
