"""Chunk-corpus statistics tests — §5.14.

Hand-checked expectations over a small RU + EN corpus built on the §5.9 chunk
contract: ``n`` counts every chunk (empty ones included), ``total_tokens`` sums
the stored ``token_count``, ``avg_tokens`` is the 2-dp mean, ``by_type`` /
``by_doc`` are first-seen-order histograms, whitespace-only chunks are flagged
in ``empty``, an empty corpus folds to all zeros, and ``as_dict`` has the exact
canonical shape.
"""

from __future__ import annotations

from kg_extractors.chunk_contract import Chunk, ChunkType
from kg_extractors.chunk_stats import ChunkStats, chunk_stats


def _mk(**over: object) -> Chunk:
    """Build a baseline chunk, overriding fields per test (no validation)."""
    base: dict[str, object] = {
        "chunk_id": "doc1:0",
        "doc_id": "doc1",
        "text": "Yield strength 350 MPa",
        "chunk_type": ChunkType.PROSE.value,
        "section": "Results",
        "page": 1,
        "token_count": 4,
        "char_start": 0,
        "char_end": 22,
    }
    base.update(over)
    return Chunk(**base)  # type: ignore[arg-type]


def _corpus() -> list[Chunk]:
    """A 5-chunk RU+EN corpus: docs A/B, 3 kinds, one whitespace-only chunk.

    tokens 4+6+2+0+8 = 20; by_type prose=3/table_row=1/caption=1;
    by_doc A=3/B=2; the caption chunk «   » is empty/whitespace-only.
    """
    return [
        _mk(chunk_id="A:0", doc_id="A", chunk_type="prose", token_count=4),
        _mk(chunk_id="A:1", doc_id="A", chunk_type="table_row", token_count=6, text="Fe | 18 | 8"),
        _mk(chunk_id="B:0", doc_id="B", chunk_type="prose", token_count=2, text="Медный купорос"),
        _mk(chunk_id="B:1", doc_id="B", chunk_type="caption", token_count=0, text="   "),
        _mk(chunk_id="A:2", doc_id="A", chunk_type="prose", token_count=8, text="Образец отжигали"),
    ]


def test_n_counts_all_chunks() -> None:
    # Every chunk counts, including the whitespace-only one.
    assert chunk_stats(_corpus()).n == 5


def test_total_tokens_sum() -> None:
    assert chunk_stats(_corpus()).total_tokens == 20


def test_avg_tokens_mean() -> None:
    # 20 tokens / 5 chunks == 4.0.
    assert chunk_stats(_corpus()).avg_tokens == 4.0


def test_avg_tokens_rounded_to_two_dp() -> None:
    # 7 tokens / 3 chunks == 2.333… → rounded to 2.33.
    chunks = [
        _mk(chunk_id="d:0", token_count=1),
        _mk(chunk_id="d:1", token_count=2),
        _mk(chunk_id="d:2", token_count=4),
    ]
    stats = chunk_stats(chunks)
    assert stats.total_tokens == 7
    assert stats.avg_tokens == 2.33


def test_by_type_histogram() -> None:
    stats = chunk_stats(_corpus())
    assert stats.by_type == {"prose": 3, "table_row": 1, "caption": 1}
    # First-seen key order is preserved (prose seen first, caption last).
    assert list(stats.by_type.keys()) == ["prose", "table_row", "caption"]


def test_by_doc_histogram() -> None:
    stats = chunk_stats(_corpus())
    assert stats.by_doc == {"A": 3, "B": 2}
    assert list(stats.by_doc.keys()) == ["A", "B"]
    # Sum of the histogram equals the chunk count.
    assert sum(stats.by_doc.values()) == stats.n


def test_empty_chunks_flagged() -> None:
    stats = chunk_stats(_corpus())
    # Only the whitespace-only caption chunk is flagged.
    assert stats.empty == ["B:1"]
    assert stats.has_empty is True
    # A flagged chunk still counts toward n and both histograms.
    assert stats.by_type["caption"] == 1
    assert stats.by_doc["B"] == 2


def test_empty_and_missing_text_both_flagged() -> None:
    chunks = [
        _mk(chunk_id="c:0", text="real text", token_count=2),
        _mk(chunk_id="c:1", text="", token_count=0),
        _mk(chunk_id="c:2", text="\t\n  ", token_count=0),
    ]
    stats = chunk_stats(chunks)
    assert stats.empty == ["c:1", "c:2"]
    assert stats.n == 3


def test_empty_corpus_all_zeros() -> None:
    stats = chunk_stats([])
    assert stats.n == 0
    assert stats.total_tokens == 0
    assert stats.avg_tokens == 0.0
    assert stats.by_type == {}
    assert stats.by_doc == {}
    assert stats.empty == []
    assert stats.has_empty is False


def test_as_dict_shape() -> None:
    stats = chunk_stats(_corpus())
    d = stats.as_dict()
    assert set(d.keys()) == {"n", "total_tokens", "avg_tokens", "by_type", "by_doc", "empty"}
    assert d == {
        "n": 5,
        "total_tokens": 20,
        "avg_tokens": 4.0,
        "by_type": {"prose": 3, "table_row": 1, "caption": 1},
        "by_doc": {"A": 3, "B": 2},
        "empty": ["B:1"],
    }
    # as_dict deep-copies containers — mutating the view never touches the frozen record.
    d_by_type = d["by_type"]
    assert isinstance(d_by_type, dict)
    d_by_type["prose"] = 999
    assert stats.by_type["prose"] == 3


def test_as_dict_matches_frozen_type() -> None:
    stats = chunk_stats(_corpus())
    assert isinstance(stats, ChunkStats)
    # Reconstructing from the dict reproduces an equal record.
    d = stats.as_dict()
    assert ChunkStats(**d) == stats  # type: ignore[arg-type]
