"""Tests for §13.20 semantic search over long-term Store memory."""

from __future__ import annotations

from agent_service.memory_semantic_index import MemoryMatch, cosine, search_memory


def test_cosine_identical_vectors_is_one() -> None:
    assert cosine([1, 0], [1, 0]) == 1.0


def test_cosine_orthogonal_vectors_is_zero() -> None:
    assert cosine([1, 0], [0, 1]) == 0.0


def test_cosine_zero_norm_returns_zero() -> None:
    assert cosine([0, 0], [1, 1]) == 0.0
    assert cosine([1, 1], [0, 0]) == 0.0


def _record(key: str, embedding: list[float], expires_at: float | None = None) -> dict:
    return {"key": key, "value": {"k": key}, "embedding": embedding, "expires_at": expires_at}


def test_search_orders_by_descending_score() -> None:
    records = [
        _record("far", [0.0, 1.0]),  # cosine with [1,0] == 0.0
        _record("near", [1.0, 0.0]),  # cosine with [1,0] == 1.0
        _record("mid", [1.0, 1.0]),  # cosine with [1,0] ~= 0.707
    ]
    out = search_memory(records, [1.0, 0.0], top_k=3, now=0.0)
    assert [m.key for m in out] == ["near", "mid", "far"]
    scores = [m.score for m in out]
    assert scores == sorted(scores, reverse=True)


def test_expired_record_excluded_none_kept() -> None:
    records = [
        _record("dead", [1.0, 0.0], expires_at=5.0),  # 5 <= now=10 → expired
        _record("alive", [1.0, 0.0], expires_at=None),  # never expires
    ]
    out = search_memory(records, [1.0, 0.0], top_k=5, now=10.0)
    assert [m.key for m in out] == ["alive"]


def test_expires_at_equal_now_is_expired() -> None:
    # expires_at <= now → dropped (boundary at exactly now).
    records = [_record("boundary", [1.0, 0.0], expires_at=10.0)]
    out = search_memory(records, [1.0, 0.0], top_k=5, now=10.0)
    assert out == []


def test_min_score_filters_low_score() -> None:
    records = [_record("half", [1.0, 1.0])]  # cosine with [1,0] ~= 0.707 (~0.5-ish, <0.9)
    # A 0.5-scoring record: use orthogonal-ish giving exactly 0.5 via [1, sqrt(3)].
    half = [{"key": "h", "value": {}, "embedding": [1.0, 3.0**0.5], "expires_at": None}]
    out = search_memory(half, [1.0, 0.0], top_k=5, now=0.0, min_score=0.9)
    assert out == []
    # And without the threshold it survives.
    kept = search_memory(half, [1.0, 0.0], top_k=5, now=0.0, min_score=0.0)
    assert len(kept) == 1
    assert abs(kept[0].score - 0.5) < 1e-9
    assert records  # keep name referenced


def test_top_k_truncates() -> None:
    records = [
        _record("a", [1.0, 0.0]),
        _record("b", [1.0, 0.1]),
        _record("c", [1.0, 0.2]),
    ]
    out = search_memory(records, [1.0, 0.0], top_k=1, now=0.0)
    assert len(out) == 1


def test_equal_scores_break_ties_by_ascending_key() -> None:
    records = [
        _record("zebra", [1.0, 0.0]),
        _record("apple", [1.0, 0.0]),
    ]
    out = search_memory(records, [1.0, 0.0], top_k=5, now=0.0)
    assert [m.key for m in out] == ["apple", "zebra"]
    assert out[0].score == out[1].score


def test_top_k_zero_returns_empty() -> None:
    records = [_record("a", [1.0, 0.0])]
    assert search_memory(records, [1.0, 0.0], top_k=0, now=0.0) == []


def test_memory_match_as_dict_keys() -> None:
    match = MemoryMatch(key="k", score=0.5, value={"a": 1})
    assert set(match.as_dict().keys()) == {"key", "score", "value"}
    assert match.as_dict() == {"key": "k", "score": 0.5, "value": {"a": 1}}
