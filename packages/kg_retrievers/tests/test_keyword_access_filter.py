"""Tests for the Mode-B keyword access-filter clause builder (§19.3).

RU: Проверяет клаузу фильтра доступа keyword-стора (OpenSearch/BM25).
EN: Verifies the OpenSearch/BM25 keyword-store access-filter clause.
"""

from __future__ import annotations

from kg_retrievers.access_filter import AccessScope, SourceMeta
from kg_retrievers.keyword_access_filter import (
    KeywordFilterResult,
    bm25_terms,
    keyword_filter_result,
    opensearch_access_filter,
)


def _scope(
    user_id: str = "u1",
    labs: frozenset[str] = frozenset(),
    owned: frozenset[str] = frozenset(),
    is_admin: bool = False,
) -> AccessScope:
    return AccessScope(
        user_id=user_id,
        labs=labs,
        owned_source_ids=owned,
        is_admin=is_admin,
    )


def _public(sid: str, owner: str = "owner-x") -> SourceMeta:
    return SourceMeta(sid, "public", frozenset(), owner)


def _lab(sid: str, labs: frozenset[str], owner: str = "owner-x") -> SourceMeta:
    return SourceMeta(sid, "lab_restricted", labs, owner)


def _private(sid: str, owner: str) -> SourceMeta:
    return SourceMeta(sid, "private", frozenset(), owner)


def test_admin_scope_returns_empty_clause() -> None:
    # Assertion (1): admin -> {} (unrestricted).
    scope = _scope(is_admin=True)
    sources = [_public("s1"), _private("s2", "someone")]
    assert opensearch_access_filter(scope, sources) == {}


def test_public_visible_to_non_admin_non_owner() -> None:
    # Assertion (2): public source id appears for a non-admin non-owner caller.
    scope = _scope(user_id="stranger")
    sources = [_public("pub-1", owner="other")]
    terms = bm25_terms(scope, sources)
    assert "pub-1" in terms
    clause = opensearch_access_filter(scope, sources)
    assert clause["bool"]["filter"][0]["terms"]["source_id"] == ["pub-1"]


def test_lab_restricted_visible_only_on_lab_intersection() -> None:
    # Assertion (3): lab_restricted visible only when scope.labs meets allowed labs.
    src = _lab("lab-1", frozenset({"labA"}), owner="other")
    member = _scope(user_id="stranger", labs=frozenset({"labA", "labB"}))
    outsider = _scope(user_id="stranger", labs=frozenset({"labZ"}))
    assert "lab-1" in bm25_terms(member, [src])
    assert "lab-1" not in bm25_terms(outsider, [src])


def test_private_visible_only_to_owner() -> None:
    # Assertion (4): private id appears only for its owner.
    src = _private("priv-1", owner="alice")
    owner = _scope(user_id="alice")
    other = _scope(user_id="bob")
    assert bm25_terms(owner, [src]) == ("priv-1",)
    assert bm25_terms(other, [src]) == ()


def test_terms_sorted_and_deduplicated() -> None:
    # Assertion (5): sorted, no duplicates when two SourceMeta share an id.
    scope = _scope(user_id="stranger")
    sources = [
        _public("z-src"),
        _public("a-src"),
        _public("a-src"),  # duplicate id across two SourceMeta
        _public("m-src"),
    ]
    terms = bm25_terms(scope, sources)
    assert terms == ("a-src", "m-src", "z-src")
    assert len(terms) == len(set(terms))


def test_empty_visibility_yields_empty_terms_not_empty_dict() -> None:
    # Assertion (6): empty visibility -> clause with empty terms, never {}.
    scope = _scope(user_id="nobody")
    sources = [_private("priv-1", owner="alice")]
    clause = opensearch_access_filter(scope, sources)
    assert clause == {"bool": {"filter": [{"terms": {"source_id": []}}]}}
    assert clause != {}


def test_non_admin_never_yields_empty_dict() -> None:
    # Assertion (7): a non-admin scope never returns {}.
    scope = _scope(user_id="nobody")
    # Even with no visible sources at all:
    assert opensearch_access_filter(scope, []) != {}
    assert opensearch_access_filter(scope, [_public("p")]) != {}


def test_bm25_terms_equals_clause_terms() -> None:
    # Assertion (8): bm25_terms equals the terms list inside the clause.
    scope = _scope(user_id="stranger", labs=frozenset({"labA"}))
    sources = [
        _public("pub"),
        _lab("lab", frozenset({"labA"})),
        _private("priv", owner="stranger"),
    ]
    terms = bm25_terms(scope, sources)
    clause = opensearch_access_filter(scope, sources)
    assert list(terms) == clause["bool"]["filter"][0]["terms"]["source_id"]


def test_keyword_filter_result_as_dict_roundtrip() -> None:
    scope = _scope(user_id="stranger")
    sources = [_public("b"), _public("a")]
    result = keyword_filter_result(scope, sources)
    assert isinstance(result, KeywordFilterResult)
    assert result.is_admin is False
    assert result.source_ids == ("a", "b")
    assert result.as_dict() == {
        "is_admin": False,
        "source_ids": ["a", "b"],
        "clause": {"bool": {"filter": [{"terms": {"source_id": ["a", "b"]}}]}},
    }


def test_keyword_filter_result_admin_clause_empty() -> None:
    scope = _scope(is_admin=True)
    result = keyword_filter_result(scope, [_public("a")])
    assert result.is_admin is True
    assert result.clause == {}
    assert result.source_ids == ("a",)
