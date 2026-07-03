"""Tests for §12.3 Mode B late-interaction MaxSim rescoring."""

from __future__ import annotations

import math

from kg_retrievers.late_interaction import LateInteractionScore, maxsim, rescore


def test_identical_single_token_maxsim_is_one() -> None:
    # Один совпадающий unit-токен запроса и документа -> cos == 1.0.
    assert maxsim([[1.0, 0.0]], [[1.0, 0.0]]) == 1.0


def test_orthogonal_single_tokens_maxsim_is_zero() -> None:
    # Ортогональные unit-токены -> cos == 0.0.
    assert maxsim([[1.0, 0.0]], [[0.0, 1.0]]) == 0.0


def test_two_query_tokens_each_matching_distinct_doc_token() -> None:
    # Каждый токен запроса точно совпадает с отдельным токеном документа -> 2.0.
    q = [[1.0, 0.0], [0.0, 1.0]]
    d = [[1.0, 0.0], [0.0, 1.0]]
    assert maxsim(q, d) == 2.0


def test_cosine_ignores_magnitude() -> None:
    # Косинус нормируется на длины: масштаб не влияет.
    assert math.isclose(maxsim([[3.0, 0.0]], [[5.0, 0.0]]), 1.0)


def test_empty_doc_vectors_maxsim_is_zero() -> None:
    assert maxsim([[1.0, 0.0]], []) == 0.0


def test_empty_query_vectors_maxsim_is_zero() -> None:
    assert maxsim([], [[1.0, 0.0]]) == 0.0


def test_zero_norm_vector_contributes_zero() -> None:
    # Вырожденный zero-norm токен документа не совпадает ни с чем.
    assert maxsim([[1.0, 0.0]], [[0.0, 0.0]]) == 0.0


def test_rescore_orders_higher_maxsim_first() -> None:
    q = [[1.0, 0.0]]
    docs = {
        "low": [[0.0, 1.0]],  # ортогонален -> 0.0
        "high": [[1.0, 0.0]],  # совпадает -> 1.0
    }
    ranked = rescore(q, docs)
    assert [s.hit_id for s in ranked] == ["high", "low"]
    assert ranked[0].maxsim == 1.0
    assert ranked[1].maxsim == 0.0


def test_token_hits_counts_positive_best_matches() -> None:
    # Один совпадающий + один ортогональный токен запроса -> token_hits == 1.
    q = [[1.0, 0.0], [0.0, 1.0]]
    d = [[1.0, 0.0]]  # совпадает только с первым токеном запроса
    ranked = rescore(q, {"doc": d})
    assert ranked[0].token_hits == 1
    assert ranked[0].maxsim == 1.0


def test_token_hits_two_when_both_match() -> None:
    q = [[1.0, 0.0], [0.0, 1.0]]
    d = [[1.0, 0.0], [0.0, 1.0]]
    ranked = rescore(q, {"doc": d})
    assert ranked[0].token_hits == 2
    assert ranked[0].maxsim == 2.0


def test_rescore_top_n_truncates() -> None:
    q = [[1.0, 0.0]]
    docs = {
        "a": [[1.0, 0.0]],
        "b": [[0.9, 0.1]],
        "c": [[0.0, 1.0]],
    }
    ranked = rescore(q, docs, top_n=2)
    assert len(ranked) == 2
    assert ranked[0].hit_id == "a"


def test_rescore_ties_break_on_hit_id() -> None:
    q = [[1.0, 0.0]]
    docs = {"zeta": [[1.0, 0.0]], "alpha": [[1.0, 0.0]]}
    ranked = rescore(q, docs)
    assert [s.hit_id for s in ranked] == ["alpha", "zeta"]


def test_rescore_empty_docs_returns_empty() -> None:
    assert rescore([[1.0, 0.0]], {}) == []


def test_as_dict_keys_exact() -> None:
    score = LateInteractionScore(hit_id="x", maxsim=1.5, token_hits=2)
    assert score.as_dict() == {"hit_id": "x", "maxsim": 1.5, "token_hits": 2}


def test_dataclass_is_frozen() -> None:
    score = LateInteractionScore(hit_id="x", maxsim=1.0, token_hits=1)
    try:
        score.maxsim = 2.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("LateInteractionScore must be frozen")
