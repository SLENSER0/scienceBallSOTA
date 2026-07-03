"""Chunk output-contract tests — serialization boundary (§5.9).

Hand-checked expectations over RU + EN text: all three chunk kinds are
accepted, the JSONL round-trip preserves every field, the whitespace/word
tokenizer counts Cyrillic + Latin correctly, ``validate`` rejects empty text /
negative offsets / unknown types, ``as_dict`` has the exact canonical shape,
and an empty chunk list serializes to the empty string.
"""

from __future__ import annotations

import json

import pytest

from kg_extractors.chunk_contract import (
    Chunk,
    ChunkType,
    chunks_from_jsonl,
    chunks_to_jsonl,
    count_tokens,
)

_FIELDS = {
    "chunk_id",
    "doc_id",
    "text",
    "chunk_type",
    "section",
    "page",
    "token_count",
    "char_start",
    "char_end",
}


def _mk(**over: object) -> Chunk:
    """Build a valid baseline chunk, overriding fields per test."""
    base: dict[str, object] = {
        "chunk_id": "doc1:0",
        "doc_id": "doc1",
        "text": "Yield strength 350 MPa",
        "chunk_type": ChunkType.PROSE.value,
        "section": "Results",
        "page": 3,
        "token_count": 4,
        "char_start": 10,
        "char_end": 32,
    }
    base.update(over)
    return Chunk(**base)  # type: ignore[arg-type]


def test_three_chunk_types_accepted() -> None:
    for kind in (ChunkType.PROSE, ChunkType.TABLE_ROW, ChunkType.CAPTION):
        chunk = _mk(chunk_type=kind.value)
        # validate() returns self and does not raise for any valid kind.
        assert chunk.validate() is chunk
        assert chunk.chunk_type == kind.value
    assert {ChunkType.PROSE.value, ChunkType.TABLE_ROW.value, ChunkType.CAPTION.value} == {
        "prose",
        "table_row",
        "caption",
    }


def test_jsonl_round_trip_preserves_fields() -> None:
    chunks = [
        _mk(chunk_id="d:0", chunk_type="prose", text="Медный купорос применяют."),
        _mk(chunk_id="d:1", chunk_type="table_row", text="Fe | 18 | 8", page=4, char_end=21),
        _mk(chunk_id="d:2", chunk_type="caption", text="Рис. 1. Микроструктура.", page=5),
    ]
    restored = chunks_from_jsonl(chunks_to_jsonl(chunks))
    assert restored == chunks
    # A trailing newline must not create a phantom chunk (lossless).
    assert chunks_from_jsonl(chunks_to_jsonl(chunks) + "\n") == chunks


def test_jsonl_line_count_and_json_validity() -> None:
    chunks = [_mk(chunk_id="d:0"), _mk(chunk_id="d:1"), _mk(chunk_id="d:2")]
    text = chunks_to_jsonl(chunks)
    lines = text.split("\n")
    assert len(lines) == 3
    # Each line is standalone valid JSON with the full field set.
    for line, chunk in zip(lines, chunks, strict=True):
        assert json.loads(line) == chunk.as_dict()


def test_count_tokens_ru_and_en() -> None:
    assert count_tokens("медный купорос") == 2
    assert count_tokens("Yield strength was 350 MPa") == 5
    # Hyphen separates alloy notation into distinct word tokens.
    assert count_tokens("Fe-18Cr-8Ni alloy") == 4
    # Образец, Fe, 18Cr, отжигали, при, 1050, C → 7 (hyphen splits Fe-18Cr).
    assert count_tokens("Образец Fe-18Cr отжигали при 1050 C") == 7
    assert count_tokens("") == 0
    assert count_tokens("   \t\n ") == 0


def test_validate_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _mk(text="").validate()
    with pytest.raises(ValueError, match="non-empty"):
        _mk(text="   \n\t ").validate()


def test_validate_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="char_start"):
        _mk(char_start=-1).validate()
    with pytest.raises(ValueError, match="char_end"):
        _mk(char_start=0, char_end=-5).validate()
    # Reversed offsets (end < start) are also rejected.
    with pytest.raises(ValueError, match="char_end"):
        _mk(char_start=20, char_end=10).validate()


def test_validate_rejects_negative_token_count() -> None:
    with pytest.raises(ValueError, match="token_count"):
        _mk(token_count=-1).validate()


def test_as_dict_shape() -> None:
    chunk = _mk(chunk_id="d:7", chunk_type=ChunkType.CAPTION.value, section="Fig", page=2)
    d = chunk.as_dict()
    assert set(d.keys()) == _FIELDS
    # chunk_type is projected as a bare string, not an Enum repr.
    assert d["chunk_type"] == "caption"
    assert isinstance(d["chunk_type"], str)
    assert d["chunk_id"] == "d:7"
    assert d["section"] == "Fig"
    assert d["page"] == 2
    assert d == {
        "chunk_id": "d:7",
        "doc_id": "doc1",
        "text": "Yield strength 350 MPa",
        "chunk_type": "caption",
        "section": "Fig",
        "page": 2,
        "token_count": 4,
        "char_start": 10,
        "char_end": 32,
    }


def test_validate_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="unknown chunk_type"):
        _mk(chunk_type="figure").validate()
    with pytest.raises(ValueError, match="unknown chunk_type"):
        _mk(chunk_type="").validate()


def test_empty_list_serializes_to_empty_string() -> None:
    assert chunks_to_jsonl([]) == ""
    assert chunks_from_jsonl("") == []
    # Whitespace-only input also yields no chunks.
    assert chunks_from_jsonl("  \n\n  ") == []
