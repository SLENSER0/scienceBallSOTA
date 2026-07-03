"""§15.2 tests: deterministic gap dedup_key + duplicate collapse (hand-checkable).

RU: Проверяем инвариантность ключа к порядку/повторам subject-id, зависимость от
``gap_type``, префикс ключа, а также свёртку :func:`merge_gaps` (макс-score
представитель, union evidence_ids, счётчик схлопнутых) и проекцию ``as_dict``.
EN: Verify key invariance to subject-id order/repeats, dependence on ``gap_type``,
the key prefix, plus :func:`merge_gaps` collapse (max-score survivor, evidence union,
collapsed counter) and the ``as_dict`` projection.
"""

from __future__ import annotations

from kg_retrievers.gap_dedup_key import DedupResult, gap_dedup_key, merge_gaps


def test_key_order_and_dup_invariant() -> None:
    """subject-id order and duplicates do not change the key (§15.2)."""
    assert gap_dedup_key("missing_unit", ["b", "a"]) == gap_dedup_key(
        "missing_unit", ["a", "b", "a"]
    )


def test_key_depends_on_gap_type() -> None:
    """Same subject set but different gap_type → different key (§15.2)."""
    same_subjects = ["a", "b"]
    assert gap_dedup_key("missing_unit", same_subjects) != gap_dedup_key(
        "missing_source", same_subjects
    )


def test_key_prefix() -> None:
    """Key starts with 'gap:<gap_type>:' (§15.2)."""
    key = gap_dedup_key("missing_unit", ["a", "b"])
    assert key.startswith("gap:missing_unit:")
    # 'gap:' + 'missing_unit' + ':' + 12 hex chars
    assert len(key) == len("gap:missing_unit:") + 12


def test_merge_same_key_keeps_max_score_and_unions_evidence() -> None:
    """Two gaps with the same key collapse into the higher-scored survivor (§15.2)."""
    key = gap_dedup_key("missing_unit", ["a", "b"])
    low = {"dedup_key": key, "score": 0.4, "evidence_ids": ["e1", "e2"]}
    high = {"dedup_key": key, "score": 0.9, "evidence_ids": ["e2", "e3"]}
    result = merge_gaps([low, high])
    assert len(result.kept) == 1
    assert result.collapsed == 1
    assert result.kept[0]["score"] == 0.9
    # Evidence of both is unioned in the survivor (order-preserving, no dups).
    assert result.kept[0]["evidence_ids"] == ["e1", "e2", "e3"]
    assert result.keys == (key,)


def test_merge_distinct_keys_kept_separately() -> None:
    """Two distinct keys → nothing collapses, both survive (§15.2)."""
    g1 = {"gap_type": "missing_unit", "subject_ids": ["a"], "score": 0.5}
    g2 = {"gap_type": "missing_unit", "subject_ids": ["b"], "score": 0.5}
    result = merge_gaps([g1, g2])
    assert result.collapsed == 0
    assert len(result.kept) == 2


def test_merge_computes_key_from_fields() -> None:
    """Gaps without precomputed dedup_key collapse via computed gap_type+subject_ids (§15.2)."""
    # Same gap_type, same subject set in different order → same computed key.
    g1 = {"gap_type": "missing_unit", "subject_ids": ["b", "a"], "score": 0.2}
    g2 = {"gap_type": "missing_unit", "subject_ids": ["a", "b"], "score": 0.7}
    result = merge_gaps([g1, g2])
    assert result.collapsed == 1
    assert len(result.kept) == 1
    assert result.kept[0]["score"] == 0.7
    assert result.keys[0] == gap_dedup_key("missing_unit", ["a", "b"])


def test_as_dict_exposes_collapsed_and_keys() -> None:
    """DedupResult.as_dict exposes collapsed and keys (§15.2, house style)."""
    result = DedupResult(kept=({"score": 0.9},), collapsed=1, keys=("gap:x:abc",))
    projected = result.as_dict()
    assert projected["collapsed"] == 1
    assert projected["keys"] == ["gap:x:abc"]
    assert projected["kept"] == [{"score": 0.9}]


def test_empty_input() -> None:
    """Empty input → empty, zero-collapse result (§15.2)."""
    result = merge_gaps([])
    assert result.kept == ()
    assert result.collapsed == 0
    assert result.keys == ()
