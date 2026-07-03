"""Hand-checked tests for retrieval-hit dedup (§12.14): exact-by-key + near-dup by text.

Каждое ожидаемое значение посчитано вручную: для near-dup ratio'ы взяты из
:class:`difflib.SequenceMatcher` (``2·M/T``), например ``"abcdefgh"`` vs ``"abcdxfgh"`` →
``14/16 = 0.875``; ``"hello world"`` vs ``"hello world!"`` → ``22/23 ≈ 0.9565``.
"""

from __future__ import annotations

from kg_retrievers.dedup_hits import dedup_hits, near_dup_by_text

# ---------------------------------------------------------------------------
# dedup_hits — exact dedup by key, keep max score, preserve first-seen order
# ---------------------------------------------------------------------------


def test_dedup_keeps_max_score_per_id() -> None:
    """Same id twice → one representative carrying the higher score and its metadata."""
    hits = [
        {"id": "x", "score": 0.5, "text": "low"},
        {"id": "x", "score": 0.9, "text": "high"},
        {"id": "y", "score": 0.3, "text": "solo"},
    ]
    out = dedup_hits(hits)
    assert [h["id"] for h in out] == ["x", "y"]
    assert [h["score"] for h in out] == [0.9, 0.3]
    # Representative is the *higher-scored* x hit, so its text/metadata win.
    assert out[0]["text"] == "high"


def test_dedup_preserves_first_seen_order() -> None:
    """Order follows first appearance of each key even when a dup arrives later."""
    hits = [
        {"id": "a", "score": 0.5},
        {"id": "b", "score": 0.4},
        {"id": "a", "score": 0.9},  # higher, but 'a' already first-seen at index 0
        {"id": "c", "score": 0.3},
    ]
    out = dedup_hits(hits)
    assert [h["id"] for h in out] == ["a", "b", "c"]
    assert [h["score"] for h in out] == [0.9, 0.4, 0.3]


def test_dedup_ties_keep_first_representative() -> None:
    """Equal score → first-seen representative is kept (strict > update only)."""
    hits = [
        {"id": "a", "score": 0.7, "text": "first"},
        {"id": "a", "score": 0.7, "text": "second"},
    ]
    out = dedup_hits(hits)
    assert len(out) == 1
    assert out[0]["text"] == "first"


def test_dedup_custom_key() -> None:
    """Grouping keys off ``doc_id`` collapses per-document, keeping max score each."""
    hits = [
        {"id": "c1", "doc_id": "D1", "score": 0.4},
        {"id": "c2", "doc_id": "D2", "score": 0.8},
        {"id": "c3", "doc_id": "D1", "score": 0.6},  # beats c1 within D1
    ]
    out = dedup_hits(hits, key="doc_id")
    assert [h["doc_id"] for h in out] == ["D1", "D2"]
    assert [h["id"] for h in out] == ["c3", "c2"]
    assert [h["score"] for h in out] == [0.6, 0.8]


def test_dedup_no_duplicates_returns_all_in_order() -> None:
    """All keys distinct → every hit survives, input order preserved verbatim."""
    hits = [
        {"id": "a", "score": 0.1},
        {"id": "b", "score": 0.2},
        {"id": "c", "score": 0.3},
    ]
    out = dedup_hits(hits)
    assert [h["id"] for h in out] == ["a", "b", "c"]


def test_dedup_empty_returns_empty() -> None:
    """Empty input → []."""
    assert dedup_hits([]) == []


def test_dedup_single_hit() -> None:
    """A lone hit passes through unchanged (as a copy)."""
    hit = {"id": "only", "score": 0.42, "text": "t"}
    out = dedup_hits([hit])
    assert out == [{"id": "only", "score": 0.42, "text": "t"}]
    assert out[0] is not hit  # returned as a copy, input not aliased


def test_dedup_does_not_mutate_input() -> None:
    """Source dicts are untouched; output holds independent copies."""
    hits = [{"id": "a", "score": 0.5}, {"id": "a", "score": 0.9}]
    out = dedup_hits(hits)
    out[0]["score"] = 111.0
    assert hits[0]["score"] == 0.5
    assert hits[1]["score"] == 0.9


# ---------------------------------------------------------------------------
# near_dup_by_text — collapse near-identical text via difflib ratio
# ---------------------------------------------------------------------------


def test_near_dup_collapses_similar_text() -> None:
    """ratio('hello world','hello world!')≈0.9565 ≥ 0.9 → the two collapse into one."""
    hits = [
        {"id": "a", "score": 0.6, "text": "hello world"},
        {"id": "b", "score": 0.9, "text": "hello world!"},
    ]
    out = near_dup_by_text(hits, threshold=0.9)
    assert len(out) == 1
    # Higher-scored 'b' becomes the cluster representative.
    assert out[0]["id"] == "b"
    assert out[0]["score"] == 0.9


def test_near_dup_keeps_distinct_text() -> None:
    """ratio('iron ore','copper smelting')≈0.174 < 0.9 → both kept, order preserved."""
    hits = [
        {"id": "a", "score": 0.8, "text": "iron ore"},
        {"id": "b", "score": 0.7, "text": "copper smelting"},
    ]
    out = near_dup_by_text(hits, threshold=0.9)
    assert [h["id"] for h in out] == ["a", "b"]


def test_near_dup_threshold_respected() -> None:
    """ratio('abcdefgh','abcdxfgh')=0.875: kept apart at 0.9, collapsed at 0.85."""
    hits = [
        {"id": "a", "score": 0.5, "text": "abcdefgh"},
        {"id": "b", "score": 0.6, "text": "abcdxfgh"},
    ]
    # 0.875 < 0.9 → NOT near-duplicates.
    strict = near_dup_by_text(hits, threshold=0.9)
    assert [h["id"] for h in strict] == ["a", "b"]
    # 0.875 >= 0.85 → collapse into the higher-scored 'b'.
    loose = near_dup_by_text(hits, threshold=0.85)
    assert len(loose) == 1
    assert loose[0]["id"] == "b"


def test_near_dup_preserves_cluster_position_and_first_rep_on_tie() -> None:
    """Near-dup keeps the earlier cluster's slot; equal score keeps the first rep."""
    hits = [
        {"id": "first", "score": 0.9, "text": "The quick brown fox"},
        {"id": "distinct", "score": 0.8, "text": "iron ore concentrate"},
        {"id": "dup", "score": 0.9, "text": "The quick brown fox."},  # ~0.974 vs 'first'
    ]
    out = near_dup_by_text(hits, threshold=0.9)
    # 'dup' folds into 'first' cluster; equal score → 'first' stays representative.
    assert [h["id"] for h in out] == ["first", "distinct"]


def test_near_dup_empty_returns_empty() -> None:
    """Empty input → []."""
    assert near_dup_by_text([]) == []


def test_near_dup_single_hit() -> None:
    """A lone hit forms its own cluster and passes through as a copy."""
    hit = {"id": "solo", "score": 0.5, "text": "unique passage"}
    out = near_dup_by_text([hit])
    assert out == [{"id": "solo", "score": 0.5, "text": "unique passage"}]
    assert out[0] is not hit


def test_near_dup_lower_scored_dup_does_not_replace_rep() -> None:
    """A later near-dup with a lower score leaves the original representative intact."""
    hits = [
        {"id": "keep", "score": 0.9, "text": "hello world"},
        {"id": "drop", "score": 0.2, "text": "hello world!"},  # ~0.9565, but lower score
    ]
    out = near_dup_by_text(hits, threshold=0.9)
    assert len(out) == 1
    assert out[0]["id"] == "keep"
    assert out[0]["score"] == 0.9


def test_near_dup_does_not_mutate_input() -> None:
    """near_dup returns copies; mutating the output leaves the source hits unchanged."""
    hits = [{"id": "a", "score": 0.5, "text": "sample text here"}]
    out = near_dup_by_text(hits)
    out[0]["text"] = "CHANGED"
    assert hits[0]["text"] == "sample text here"
