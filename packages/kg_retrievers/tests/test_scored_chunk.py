"""Hand-checked tests for the §4.5 ``ScoredChunk`` return type and RRF merge.

Каждое ожидаемое число посчитано вручную по формуле RRF §7.5 Node 6 / §12.4:
``score = Σ 1/(k+rank)`` (rank 1-based, лучший = 1, k=60 по умолчанию).
"""

from __future__ import annotations

import pytest

from kg_retrievers.scored_chunk import (
    SOURCE_OPENSEARCH,
    SOURCE_QDRANT,
    ScoredChunk,
    merge_scored,
)


# ---------------------------------------------------------------------------
# from_qdrant_hit / from_opensearch_hit — hit-dict → ScoredChunk
# ---------------------------------------------------------------------------
def test_from_qdrant_hit_maps_all_fields() -> None:
    """QdrantServerStore.search hit → every field carried, source == qdrant."""
    hit = {"id": "c1", "text": "обратный осмос", "score": 0.87, "doc_id": "doc-9", "page": 3}
    sc = ScoredChunk.from_qdrant_hit(hit)
    assert sc.id == "c1"
    assert sc.text == "обратный осмос"
    assert sc.score == 0.87
    assert sc.doc_id == "doc-9"
    assert sc.page == 3
    assert sc.material_ids == ()
    assert sc.source == SOURCE_QDRANT


def test_from_qdrant_hit_reads_material_ids_when_present() -> None:
    """A hit carrying material_ids is normalised to a tuple, not dropped."""
    hit = {"id": "c1", "text": "t", "score": 0.5, "material_ids": ["m1", "m2"]}
    sc = ScoredChunk.from_qdrant_hit(hit)
    assert sc.material_ids == ("m1", "m2")


def test_from_opensearch_hit_maps_all_fields_and_source() -> None:
    """OpenSearchKeywordStore.search hit → same mapping, source == opensearch."""
    hit = {"id": "k7", "text": "reverse osmosis", "score": 4.2, "doc_id": "d2", "page": 11}
    sc = ScoredChunk.from_opensearch_hit(hit)
    assert sc.id == "k7"
    assert sc.text == "reverse osmosis"
    assert sc.score == 4.2
    assert sc.doc_id == "d2"
    assert sc.page == 11
    assert sc.source == SOURCE_OPENSEARCH


def test_missing_optional_fields_default() -> None:
    """A minimal hit (no doc_id/page/material_ids) gets None/None/() defaults."""
    sc = ScoredChunk.from_qdrant_hit({"id": "c2", "text": "t", "score": 1.0})
    assert sc.doc_id is None
    assert sc.page is None
    assert sc.material_ids == ()
    assert sc.source == SOURCE_QDRANT


# ---------------------------------------------------------------------------
# as_dict / from_dict round-trip
# ---------------------------------------------------------------------------
def test_from_dict_missing_optional_fields_default() -> None:
    """from_dict with only id/text/score fills the optional fields with defaults."""
    sc = ScoredChunk.from_dict({"id": "c", "text": "txt", "score": 0.25})
    assert sc.doc_id is None
    assert sc.page is None
    assert sc.material_ids == ()
    assert sc.source == ""


def test_as_dict_from_dict_round_trip() -> None:
    """as_dict → from_dict reproduces the exact ScoredChunk (material_ids as list)."""
    sc = ScoredChunk(
        id="c",
        text="txt",
        score=0.5,
        doc_id="d",
        page=2,
        material_ids=("m1", "m2"),
        source=SOURCE_QDRANT,
    )
    d = sc.as_dict()
    assert d == {
        "id": "c",
        "text": "txt",
        "score": 0.5,
        "doc_id": "d",
        "page": 2,
        "material_ids": ["m1", "m2"],  # JSON-ready list, not tuple
        "source": SOURCE_QDRANT,
    }
    assert ScoredChunk.from_dict(d) == sc


# ---------------------------------------------------------------------------
# merge_scored — Reciprocal Rank Fusion (score = Σ 1/(k+rank), rank 1-based)
# ---------------------------------------------------------------------------
def _chunk(cid: str, score: float = 0.0, source: str = SOURCE_QDRANT) -> ScoredChunk:
    return ScoredChunk(id=cid, text=cid, score=score, source=source)


def test_merge_ranks_doc_in_both_first() -> None:
    """X is in both lists → fused 1/61 + 1/62 beats any single-appearance id."""
    a = [_chunk("X"), _chunk("Y")]  # ranks 1,2
    b = [_chunk("Z"), _chunk("X")]  # ranks 1,2
    merged = merge_scored(a, b, k=60)
    assert [c.id for c in merged] == ["X", "Z", "Y"]
    scores = {c.id: c.score for c in merged}
    assert abs(scores["X"] - (1.0 / 61.0 + 1.0 / 62.0)) < 1e-12  # ≈ 0.032522
    assert abs(scores["Z"] - 1.0 / 61.0) < 1e-12
    assert abs(scores["Y"] - 1.0 / 62.0) < 1e-12


def test_merge_preserves_single_list_order() -> None:
    """One list vs empty: 1/(k+rank) is strictly decreasing → input order kept."""
    a = [_chunk("A"), _chunk("B"), _chunk("C")]
    merged = merge_scored(a, [], k=60)
    assert [c.id for c in merged] == ["A", "B", "C"]
    assert abs(merged[0].score - 1.0 / 61.0) < 1e-12
    assert abs(merged[1].score - 1.0 / 62.0) < 1e-12
    assert abs(merged[2].score - 1.0 / 63.0) < 1e-12


def test_merge_empty_lists_returns_empty() -> None:
    """Both inputs empty → empty result (no crash)."""
    assert merge_scored([], []) == []


def test_merge_records_higher_scored_representative_source() -> None:
    """Duplicate id: fused score kept; metadata/source from the higher-scored side."""
    a = [ScoredChunk(id="X", text="dense", score=0.9, source=SOURCE_QDRANT)]
    b = [ScoredChunk(id="X", text="bm25", score=0.3, source=SOURCE_OPENSEARCH)]
    merged = merge_scored(a, b, k=60)
    assert len(merged) == 1
    assert merged[0].source == SOURCE_QDRANT  # 0.9 > 0.3 → qdrant representative
    assert merged[0].text == "dense"
    assert abs(merged[0].score - 2.0 / 61.0) < 1e-12  # fused 1/61 + 1/61 > either alone


def test_merge_representative_when_second_list_scores_higher() -> None:
    """Symmetric check: when list b scores higher, its metadata/source wins."""
    a = [ScoredChunk(id="X", text="dense", score=0.2, source=SOURCE_QDRANT)]
    b = [ScoredChunk(id="X", text="bm25", score=0.8, source=SOURCE_OPENSEARCH)]
    merged = merge_scored(a, b, k=60)
    assert merged[0].source == SOURCE_OPENSEARCH
    assert merged[0].text == "bm25"


def test_merge_invalid_k_raises() -> None:
    """k must be positive — a non-positive constant is rejected."""
    with pytest.raises(ValueError):
        merge_scored([_chunk("X")], [], k=0)
