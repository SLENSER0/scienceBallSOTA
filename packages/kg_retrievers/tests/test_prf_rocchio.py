"""Hand-checkable tests for Rocchio PRF query expansion (§12.3 Mode B, pure python).

Tiny fixed sparse vectors (term -> weight) so every arithmetic step is verifiable by hand.
No store, no network. RU|EN: центроид / расширение запроса.
"""

from __future__ import annotations

from kg_retrievers.prf_rocchio import RocchioResult, _centroid, rocchio_expand


def test_centroid_treats_missing_dims_as_zero() -> None:
    # Assertion (1): mean of {a:2} and {a:0,b:4} is {a:1.0, b:2.0} (b absent in first -> 0).
    assert _centroid([{"a": 2.0}, {"a": 0.0, "b": 4.0}]) == {"a": 1.0, "b": 2.0}


def test_centroid_empty_is_empty() -> None:
    assert _centroid([]) == {}


def test_relevant_reinforces_query_term() -> None:
    # Assertion (2): q'=1*q + 1*centroid(rel) - 0; a = 1.0 + 1.0 = 2.0.
    res = rocchio_expand({"a": 1.0}, [{"a": 1.0}], alpha=1.0, beta=1.0, gamma=0.0)
    assert res.vector["a"] == 2.0


def test_relevant_only_term_is_added() -> None:
    # Assertion (3): 'b' appears only in relevant docs -> surfaces as an added term.
    res = rocchio_expand({"a": 1.0}, [{"a": 1.0, "b": 4.0}], beta=1.0, gamma=0.0)
    assert "b" in res.vector
    assert "b" in res.added_terms


def test_nonrelevant_only_term_clamped_to_zero() -> None:
    # Assertion (4): 'c' strong only in non-relevant -> negative q', clamped -> dropped.
    res = rocchio_expand(
        {"a": 1.0},
        [{"a": 1.0}],
        [{"c": 10.0}],
        alpha=1.0,
        beta=1.0,
        gamma=1.0,
    )
    assert "c" not in res.vector
    assert all(w >= 0.0 for w in res.vector.values())


def test_gamma_zero_ignores_nonrelevant() -> None:
    # Assertion (5): gamma=0 makes non-relevant docs irrelevant to the result.
    with_nonrel = rocchio_expand({"a": 1.0}, [{"a": 1.0}], [{"c": 10.0}], gamma=0.0)
    without = rocchio_expand({"a": 1.0}, [{"a": 1.0}], gamma=0.0)
    assert with_nonrel.vector == without.vector


def test_top_terms_keeps_exactly_one_dim() -> None:
    # Assertion (6): top_terms=1 keeps a single (highest-weight) dimension.
    res = rocchio_expand(
        {"a": 1.0},
        [{"a": 1.0, "b": 5.0, "c": 3.0}],
        beta=1.0,
        gamma=0.0,
        top_terms=1,
    )
    assert len(res.vector) == 1
    # b has the largest weight (0.75-default overridden to beta=1 -> b = 5.0).
    assert set(res.vector) == {"b"}


def test_added_terms_excludes_original_query_terms() -> None:
    # Assertion (7): original query dims never appear in added_terms even if reinforced.
    res = rocchio_expand({"a": 1.0}, [{"a": 1.0, "b": 2.0}], beta=1.0, gamma=0.0)
    assert "a" in res.vector
    assert "a" not in res.added_terms
    assert "b" in res.added_terms


def test_as_dict_returns_coefficients() -> None:
    # Assertion (8): as_dict() round-trips the vector, added terms and coefficients.
    res = rocchio_expand({"a": 1.0}, [{"a": 1.0}], alpha=1.0, beta=0.75, gamma=0.15)
    d = res.as_dict()
    assert d["alpha"] == 1.0
    assert d["beta"] == 0.75
    assert d["gamma"] == 0.15
    assert d["vector"] == res.vector
    assert d["added_terms"] == list(res.added_terms)


def test_result_is_frozen() -> None:
    res = rocchio_expand({"a": 1.0}, [{"a": 1.0}])
    assert isinstance(res, RocchioResult)
    try:
        res.alpha = 2.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("RocchioResult must be frozen")


def test_added_terms_ordered_by_weight_desc() -> None:
    # Deterministic order: highest weight first, ties broken by term.
    res = rocchio_expand(
        {"a": 1.0},
        [{"a": 1.0, "b": 2.0, "d": 5.0}],
        beta=1.0,
        gamma=0.0,
    )
    assert res.added_terms == ("d", "b")
