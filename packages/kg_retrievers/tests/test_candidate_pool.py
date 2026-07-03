"""§12.19 tests for candidate_pool — merge/dedup/sources tracking (pure python)."""

from __future__ import annotations

from kg_retrievers.candidate_pool import CandidatePool, MergedCandidate


def test_merge_across_sources() -> None:
    """Hits from two channels collapse into one candidate per id (§12.19)."""
    pool = CandidatePool()
    pool.add("dense", [{"id": "a", "score": 0.4, "text": "alpha"}])
    pool.add("bm25", [{"id": "b", "score": 0.9, "text": "beta"}])
    merged = pool.merged()
    assert [c.id for c in merged] == ["b", "a"]
    assert [c.score for c in merged] == [0.9, 0.4]


def test_dedup_keeps_max_score() -> None:
    """Same id from two channels keeps the higher score and its text (§12.19)."""
    pool = CandidatePool()
    pool.add("dense", [{"id": "a", "score": 0.3, "text": "low"}])
    pool.add("bm25", [{"id": "a", "score": 0.8, "text": "high"}])
    merged = pool.merged()
    assert len(merged) == 1
    assert merged[0].score == 0.8
    assert merged[0].text == "high"


def test_sources_tracked() -> None:
    """All channels that contributed an id are recorded, sorted (§12.19)."""
    pool = CandidatePool()
    pool.add("bm25", [{"id": "a", "score": 0.5}])
    pool.add("dense", [{"id": "a", "score": 0.2}])
    pool.add("graph", [{"id": "a", "score": 0.1}])
    assert pool.sources_of("a") == ("bm25", "dense", "graph")
    assert pool.merged()[0].sources == ("bm25", "dense", "graph")


def test_order_by_score_desc() -> None:
    """Merged output is sorted by score descending, ties broken by id asc (§12.19)."""
    pool = CandidatePool()
    pool.add(
        "dense",
        [
            {"id": "z", "score": 0.5},
            {"id": "a", "score": 0.5},
            {"id": "m", "score": 0.7},
        ],
    )
    assert [c.id for c in pool.merged()] == ["m", "a", "z"]


def test_empty_pool() -> None:
    """A pool with no hits merges to an empty list and empty as_dict (§12.19)."""
    pool = CandidatePool()
    assert pool.merged() == []
    assert pool.as_dict() == {"candidates": []}
    assert pool.sources_of("missing") == ()


def test_single_source() -> None:
    """A single source of several hits yields one candidate each (§12.19)."""
    pool = CandidatePool()
    pool.add(
        "dense",
        [
            {"id": "a", "score": 0.1, "text": "A"},
            {"id": "b", "score": 0.2, "text": "B"},
        ],
    )
    merged = pool.merged()
    assert [(c.id, c.sources) for c in merged] == [
        ("b", ("dense",)),
        ("a", ("dense",)),
    ]


def test_as_dict() -> None:
    """as_dict emits JSON-ready projection with sources as lists (§12.19)."""
    pool = CandidatePool()
    pool.add("dense", [{"id": "a", "score": 0.6, "text": "alpha"}])
    pool.add("bm25", [{"id": "a", "score": 0.4, "text": "other"}])
    assert pool.as_dict() == {
        "candidates": [
            {"id": "a", "score": 0.6, "text": "alpha", "sources": ["bm25", "dense"]},
        ],
    }


def test_ties_keep_earlier_representative() -> None:
    """Equal scores keep the earlier-seen text representative (§12.19)."""
    pool = CandidatePool()
    pool.add("dense", [{"id": "a", "score": 0.5, "text": "first"}])
    pool.add("bm25", [{"id": "a", "score": 0.5, "text": "second"}])
    assert pool.merged()[0].text == "first"


def test_missing_id_skipped() -> None:
    """Hits without an id are ignored, not merged (§12.19)."""
    pool = CandidatePool()
    pool.add("dense", [{"score": 0.9, "text": "no-id"}, {"id": "a", "score": 0.3}])
    merged = pool.merged()
    assert [c.id for c in merged] == ["a"]


def test_merged_candidate_frozen_hashable() -> None:
    """MergedCandidate is a frozen, hashable dataclass (§12.19)."""
    c = MergedCandidate(id="a", score=0.5, text="t", sources=("dense",))
    assert hash(c) == hash(MergedCandidate(id="a", score=0.5, text="t", sources=("dense",)))
    assert c.as_dict() == {"id": "a", "score": 0.5, "text": "t", "sources": ["dense"]}
