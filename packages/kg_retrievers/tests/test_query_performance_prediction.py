"""§12.11 — tests for post-retrieval QPP predictors over fused scores."""

from __future__ import annotations

from kg_retrievers.query_performance_prediction import QPPScores, predict


def test_hand_checked_reference_case() -> None:
    # top-5 = [0.9,0.7,0.5,0.3,0.1]; mean=0.5; var = (0.16+0.04+0+0.04+0.16)/5=0.08
    # std=sqrt(0.08)=0.2828427...; nqc=std/0.5=0.5656854...
    res = predict([0.9, 0.7, 0.5, 0.3, 0.1], k=5, corpus_mean=0.0)
    assert res.mean_top == 0.5
    assert abs(res.std_dev - 0.28284271247) < 1e-9
    assert abs(res.nqc - 0.56568542495) < 1e-9
    assert abs(res.top_gap - 0.2) < 1e-12
    assert res.wig == 0.5


def test_unsorted_input_yields_same_result() -> None:
    a = predict([0.9, 0.7, 0.5, 0.3, 0.1], k=5)
    b = predict([0.3, 0.1, 0.9, 0.5, 0.7], k=5)
    assert a == b


def test_k_larger_than_length_uses_all() -> None:
    res = predict([0.9, 0.7, 0.5, 0.3, 0.1], k=100)
    assert res.mean_top == 0.5
    assert abs(res.std_dev - 0.28284271247) < 1e-9


def test_single_score_top_gap_zero() -> None:
    res = predict([0.8], k=5)
    assert res.top_gap == 0.0
    assert res.mean_top == 0.8
    assert res.std_dev == 0.0
    assert res.nqc == 0.0


def test_empty_input_all_zeros() -> None:
    res = predict([])
    assert res.nqc == 0.0
    assert res.wig == 0.0
    assert res.std_dev == 0.0
    assert res.top_gap == 0.0
    assert res.mean_top == 0.0


def test_wig_uses_corpus_mean() -> None:
    res = predict([0.9, 0.7, 0.5, 0.3, 0.1], k=5, corpus_mean=0.2)
    assert abs(res.wig - 0.3) < 1e-12  # 0.5 - 0.2


def test_nqc_zero_when_mean_top_zero() -> None:
    res = predict([0.0, 0.0, 0.0], k=3)
    assert res.mean_top == 0.0
    assert res.nqc == 0.0
    assert res.std_dev == 0.0


def test_top_gap_over_full_sorted_not_slice() -> None:
    # top_gap should reflect the two highest scores regardless of k
    res = predict([0.5, 0.9, 0.1, 0.7, 0.3], k=1)
    assert abs(res.top_gap - 0.2) < 1e-12  # 0.9 - 0.7


def test_as_dict_exposes_all_five_fields() -> None:
    res = predict([0.9, 0.7, 0.5, 0.3, 0.1], k=5)
    d = res.as_dict()
    assert set(d) == {"nqc", "wig", "std_dev", "top_gap", "mean_top"}
    assert d["mean_top"] == 0.5


def test_frozen_dataclass() -> None:
    res = QPPScores(nqc=1.0, wig=2.0, std_dev=3.0, top_gap=4.0, mean_top=5.0)
    try:
        res.nqc = 9.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("QPPScores must be frozen")
