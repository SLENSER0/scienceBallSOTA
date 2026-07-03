"""Tests for §12.4 weighted RRF fusion — hand-checkable arithmetic."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_retrievers.weighted_rrf import WRRFHit, weighted_rrf_fuse


def test_single_source_weight_two_rank_zero() -> None:
    """Один источник, вес 2.0, doc на rank 0, k=60 → score == 2/60."""
    hits = weighted_rrf_fuse({"dense": ["d"]}, weights={"dense": 2.0}, k=60)
    assert len(hits) == 1
    assert hits[0].doc_id == "d"
    assert hits[0].score == pytest.approx(2.0 / 60.0)


def test_doc_in_two_equal_sources_sums_reciprocals() -> None:
    """Doc в двух равновзвешенных источниках → сумма обоих reciprocals."""
    # both weight default 1.0; "x" at rank 0 in dense, rank 1 in sparse.
    hits = weighted_rrf_fuse({"dense": ["x"], "sparse": ["y", "x"]}, k=60)
    by_id = {h.doc_id: h for h in hits}
    expected = 1.0 / 60.0 + 1.0 / 61.0
    assert by_id["x"].score == pytest.approx(expected)
    # contributions carry both sources and sum to score.
    assert set(by_id["x"].contributions) == {"dense", "sparse"}
    assert sum(by_id["x"].contributions.values()) == pytest.approx(by_id["x"].score)


def test_zero_weight_source_contributes_nothing() -> None:
    """Источник с весом 0.0 не даёт вклада; в contributions его нет."""
    hits = weighted_rrf_fuse(
        {"dense": ["a"], "sparse": ["a"]},
        weights={"dense": 1.0, "sparse": 0.0},
        k=60,
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.doc_id == "a"
    assert "sparse" not in hit.contributions
    assert hit.contributions == {"dense": pytest.approx(1.0 / 60.0)}
    assert hit.score == pytest.approx(1.0 / 60.0)


def test_large_weight_source_outranks_rank_zero_small_weight() -> None:
    """Большой вес источника может обогнать rank-0 doc из мелковесного источника."""
    # "big" at rank 5 in a heavy source vs "small" at rank 0 in a light source.
    hits = weighted_rrf_fuse(
        {"heavy": ["p0", "p1", "p2", "p3", "p4", "big"], "light": ["small"]},
        weights={"heavy": 100.0, "light": 1.0},
        k=60,
    )
    by_id = {h.doc_id: h for h in hits}
    big_score = 100.0 / (60 + 5)
    small_score = 1.0 / (60 + 0)
    assert by_id["big"].score == pytest.approx(big_score)
    assert by_id["small"].score == pytest.approx(small_score)
    assert big_score > small_score
    # "big" should outrank "small" in the ordered output.
    order = [h.doc_id for h in hits]
    assert order.index("big") < order.index("small")


def test_larger_k_flattens_rank_gap_monotonically() -> None:
    """Больший k сглаживает разрыв rank0 vs rank1 — разница монотонно убывает."""
    rankings = {"s": ["r0", "r1"]}
    prev_gap = None
    for k in (1, 5, 20, 100, 1000):
        hits = weighted_rrf_fuse(rankings, k=k)
        by_id = {h.doc_id: h.score for h in hits}
        gap = by_id["r0"] - by_id["r1"]
        assert gap > 0.0
        if prev_gap is not None:
            assert gap < prev_gap  # монотонно уменьшается с ростом k
        prev_gap = gap


def test_ties_broken_by_doc_id() -> None:
    """Равные score → порядок по doc_id (лексикографически)."""
    # all at rank 0 of distinct equal-weight sources → identical scores.
    hits = weighted_rrf_fuse(
        {"s1": ["zebra"], "s2": ["alpha"], "s3": ["mango"]},
        k=60,
    )
    scores = {h.score for h in hits}
    assert len(scores) == 1  # all identical
    assert [h.doc_id for h in hits] == ["alpha", "mango", "zebra"]


def test_as_dict_contributions_sum_to_score() -> None:
    """as_dict() отдаёт per-source вклад, суммирующийся в score."""
    hits = weighted_rrf_fuse(
        {"dense": ["d", "e"], "sparse": ["d"]},
        weights={"dense": 2.0, "sparse": 3.0},
        k=60,
    )
    by_id = {h.doc_id: h for h in hits}
    d = by_id["d"].as_dict()
    assert d["doc_id"] == "d"
    assert set(d["contributions"]) == {"dense", "sparse"}
    assert d["contributions"]["dense"] == pytest.approx(2.0 / 60.0)
    assert d["contributions"]["sparse"] == pytest.approx(3.0 / 60.0)
    assert sum(d["contributions"].values()) == pytest.approx(d["score"])


def test_default_weight_is_one_for_missing_source() -> None:
    """Источник, отсутствующий в weights, берётся с весом 1.0."""
    hits = weighted_rrf_fuse({"unknown": ["z"]}, weights={"other": 5.0}, k=60)
    assert hits[0].score == pytest.approx(1.0 / 60.0)


def test_empty_rankings_returns_empty() -> None:
    """Пустой вход → пустой результат."""
    assert weighted_rrf_fuse({}) == []


def test_non_positive_k_raises() -> None:
    """k <= 0 недопустим (деление/сглаживание некорректно)."""
    with pytest.raises(ValueError):
        weighted_rrf_fuse({"s": ["a"]}, k=0)


def test_frozen_dataclass_immutable() -> None:
    """WRRFHit заморожен — присваивание полей запрещено."""
    hit = WRRFHit(doc_id="a", score=1.0, contributions={"s": 1.0})
    with pytest.raises(FrozenInstanceError):
        hit.score = 2.0  # type: ignore[misc]
