"""Tests for the references splitter (§5.7).

Тесты разбиения раздела «References»/«Список литературы».
"""

from __future__ import annotations

import pytest

from kg_extractors.reference_splitter import (
    ReferenceEntry,
    ReferenceList,
    find_references_block,
    split_references,
)


def test_bracket_marker_split() -> None:
    """``[1] .. [2] ..`` splits into two marker-parsed entries."""
    refs = split_references("[1] A. Foo, 2020.\n[2] B. Bar, 2021.")
    assert len(refs) == 2
    assert refs.entries[0].marker == "1"
    assert refs.entries[0].text == "A. Foo, 2020."
    assert refs.entries[1].text.startswith("B. Bar")
    assert refs.entries[1].marker == "2"


def test_numeric_dot_split() -> None:
    """``1. X\\n2. Y`` numeric-dot style splits into two entries."""
    refs = split_references("1. X\n2. Y")
    assert len(refs) == 2
    assert [entry.marker for entry in refs.entries] == ["1", "2"]
    assert refs.entries[0].text == "X"
    assert refs.entries[1].text == "Y"


def test_paren_marker_split() -> None:
    """``12) ..`` paren style parses the bare number as the marker."""
    refs = split_references("12) Zed, 2019.\n13) Qux, 2018.")
    assert len(refs) == 2
    assert refs.entries[0].marker == "12"
    assert refs.entries[1].marker == "13"


def test_blank_line_fallback() -> None:
    """No markers -> split on blank lines with ``marker is None``."""
    refs = split_references("Foo 2020\n\nBar 2021")
    assert len(refs) == 2
    assert refs.entries[0].marker is None
    assert refs.entries[1].marker is None
    assert refs.entries[0].text == "Foo 2020"
    assert refs.entries[1].text == "Bar 2021"


def test_char_offsets_slice_back_marker() -> None:
    """Marker-entry offsets slice back to the entry text within the block."""
    block = "[1] A. Foo, 2020.\n[2] B. Bar, 2021."
    refs = split_references(block)
    first = refs.entries[0]
    assert block[first.char_start : first.char_end] == first.text
    second = refs.entries[1]
    assert block[second.char_start : second.char_end] == second.text


def test_char_offsets_slice_back_blank() -> None:
    """Blank-fallback offsets also slice back to the entry text."""
    block = "Foo 2020\n\nBar 2021"
    refs = split_references(block)
    for entry in refs.entries:
        assert block[entry.char_start : entry.char_end] == entry.text


def test_find_references_block_points_after_heading() -> None:
    """``find_references_block`` start points just after the heading line."""
    text = "Intro...\nReferences\n[1] X"
    span = find_references_block(text)
    assert span is not None
    start, end = span
    assert text[start:] == "[1] X"
    assert end == len(text)


def test_find_references_block_russian_heading() -> None:
    """Russian ``Список литературы`` heading is recognised."""
    text = "Введение...\nСписок литературы\n[1] Иванов А., 2020."
    span = find_references_block(text)
    assert span is not None
    start, _ = span
    assert text[start:].startswith("[1] Иванов")


def test_find_references_block_absent() -> None:
    """No heading -> ``None``."""
    assert find_references_block("Just some prose without a bibliography.") is None


def test_end_to_end_find_then_split() -> None:
    """Locate a block then split it into two entries."""
    text = "Body text.\nReferences\n[1] A. Foo, 2020.\n[2] B. Bar, 2021."
    span = find_references_block(text)
    assert span is not None
    start, end = span
    refs = split_references(text[start:end])
    assert len(refs) == 2
    assert refs.entries[0].marker == "1"


def test_empty_block() -> None:
    """Empty / whitespace block -> empty list."""
    assert len(split_references("")) == 0
    assert len(split_references("   \n  \n")) == 0


def test_drops_empty_entries() -> None:
    """Blank markerless chunks are dropped."""
    refs = split_references("Foo 2020\n\n\n\nBar 2021")
    assert len(refs) == 2


def test_reference_list_as_dict() -> None:
    """``ReferenceList.as_dict`` mirrors entry dicts, first marker == '1'."""
    refs = split_references("[1] A. Foo, 2020.\n[2] B. Bar, 2021.")
    data = refs.as_dict()
    assert data["entries"][0]["marker"] == "1"
    assert data["entries"][0]["text"] == "A. Foo, 2020."
    assert data["entries"][1]["index"] == 1


def test_reference_entry_as_dict_roundtrip() -> None:
    """``ReferenceEntry.as_dict`` exposes every field."""
    entry = ReferenceEntry(index=0, text="X", marker="1", char_start=3, char_end=4)
    assert entry.as_dict() == {
        "index": 0,
        "text": "X",
        "marker": "1",
        "char_start": 3,
        "char_end": 4,
    }


def test_frozen_dataclasses() -> None:
    """Entries and lists are immutable."""
    from dataclasses import FrozenInstanceError

    entry = ReferenceEntry(index=0, text="X", marker=None, char_start=0, char_end=1)
    refs = ReferenceList(entries=(entry,))
    with pytest.raises(FrozenInstanceError):
        entry.text = "Y"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        refs.entries = ()  # type: ignore[misc]
