"""Tests for Qdrant-style payload filters (§4.5).

Every expectation is hand-checkable from the operator rules: ``eq`` is scalar
equality, ``in`` is set intersection, ``range`` is inclusive numeric bounds,
``exists`` is field presence; ``must`` is AND, ``must_not`` a negated AND, and a
non-empty ``should`` is OR. The ``to_qdrant`` shape mirrors ``qdrant-client``:
``match.value`` / ``match.any`` / ``range.{gte,lte}`` / ``values_count`` /
``is_empty``.
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.vector_filters import (
    FieldCondition,
    Filter,
    build_filter,
    matches,
    to_qdrant,
)


def test_eq_match() -> None:
    """``field=value`` matches an equal scalar and nothing else (§4.5)."""
    f = build_filter(status="active")
    assert matches(f, {"status": "active"})
    assert not matches(f, {"status": "inactive"})
    assert not matches(f, {})  # absent field never satisfies eq


def test_in_match() -> None:
    """``field__in`` matches set membership, incl. array-field intersection (§4.5)."""
    f = build_filter(grade__in=["A", "B"])
    assert matches(f, {"grade": "A"})
    assert matches(f, {"grade": "B"})
    assert not matches(f, {"grade": "C"})
    assert not matches(f, {})
    assert matches(f, {"grade": ["C", "B"]})  # multi-value field intersects {A, B}
    assert not matches(f, {"grade": ["C", "D"]})


def test_range_gte_lte() -> None:
    """``__gte``/``__lte`` bound a numeric field inclusively (§4.5)."""
    f = build_filter(year__gte=2000, year__lte=2010)
    assert matches(f, {"year": 2005})
    assert matches(f, {"year": 2000})  # lower bound inclusive
    assert matches(f, {"year": 2010})  # upper bound inclusive
    assert not matches(f, {"year": 1999})
    assert not matches(f, {"year": 2011})
    assert not matches(f, {})
    # A one-sided bound leaves the other end open.
    lower = build_filter(year__gte=2000)
    assert matches(lower, {"year": 9999})
    assert not matches(lower, {"year": 1000})


def test_must_not() -> None:
    """``must_not`` excludes matching payloads; absent field passes (§4.5)."""
    f = build_filter(must_not={"deleted": True})
    assert matches(f, {"deleted": False})
    assert matches(f, {})  # field absent -> clause does not match -> allowed
    assert not matches(f, {"deleted": True})


def test_should_any() -> None:
    """A non-empty ``should`` group is satisfied by any one clause (§4.5)."""
    f = build_filter(should={"a": 1, "b": 2})
    assert matches(f, {"a": 1})
    assert matches(f, {"b": 2})
    assert matches(f, {"a": 1, "b": 999})  # one of two suffices
    assert not matches(f, {"a": 9, "b": 9})
    assert not matches(f, {})


def test_exists() -> None:
    """``__exists`` tests presence (True) or absence (False) of a field (§4.5)."""
    present = build_filter(doi__exists=True)
    assert matches(present, {"doi": "10.1/x"})
    assert not matches(present, {"title": "x"})  # field missing
    assert not matches(present, {"doi": None})  # None reads as absent
    assert not matches(present, {"doi": []})  # empty list reads as absent
    absent = build_filter(doi__exists=False)
    assert matches(absent, {"title": "x"})
    assert not matches(absent, {"doi": "10.1/x"})


def test_combined() -> None:
    """must ∧ ¬must_not ∧ (should ∨) evaluated together (§4.5)."""
    f = build_filter(
        material="steel",
        year__gte=2000,
        should={"grade__in": ["A", "B"]},
        must_not={"deleted": True},
    )
    assert matches(f, {"material": "steel", "year": 2005, "grade": "A"})
    assert not matches(f, {"material": "iron", "year": 2005, "grade": "A"})  # must eq fails
    assert not matches(f, {"material": "steel", "year": 1999, "grade": "A"})  # range fails
    assert not matches(f, {"material": "steel", "year": 2005, "grade": "C"})  # should fails
    assert not matches(  # must_not triggers
        f, {"material": "steel", "year": 2005, "grade": "A", "deleted": True}
    )


def test_to_qdrant_shape() -> None:
    """``to_qdrant`` emits the qdrant-client Filter JSON shape (§4.5)."""
    f = build_filter(
        status="active",
        tags__in=["a", "b"],
        year__gte=2000,
        year__lte=2020,
        should={"flag": True},
        must_not={"deleted": True},
    )
    q = to_qdrant(f)
    assert set(q) == {"must", "should", "must_not"}
    assert {"key": "status", "match": {"value": "active"}} in q["must"]
    assert {"key": "tags", "match": {"any": ["a", "b"]}} in q["must"]
    assert {"key": "year", "range": {"gte": 2000, "lte": 2020}} in q["must"]
    assert q["should"] == [{"key": "flag", "match": {"value": True}}]
    assert q["must_not"] == [{"key": "deleted", "match": {"value": True}}]


def test_to_qdrant_exists_and_empty() -> None:
    """``exists`` renders as ``values_count`` (present) or ``is_empty`` (absent) (§4.5)."""
    assert to_qdrant(build_filter(doi__exists=True)) == {
        "must": [{"key": "doi", "values_count": {"gte": 1}}]
    }
    assert to_qdrant(build_filter(doi__exists=False)) == {"must": [{"is_empty": {"key": "doi"}}]}
    assert to_qdrant(build_filter()) == {}  # empty filter -> qdrant match-all


def test_frozen_and_as_dict() -> None:
    """Filter/FieldCondition are frozen dataclasses with faithful ``as_dict`` (§4.5)."""
    f = build_filter(status="active")
    assert isinstance(f, Filter)
    assert isinstance(f.must[0], FieldCondition)
    assert f.as_dict() == {
        "must": [{"field": "status", "op": "eq", "value": "active"}],
        "should": [],
        "must_not": [],
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.must = ()  # type: ignore[misc]


def test_empty_filter_matches_everything() -> None:
    """A filter with no clauses admits any payload (§4.5)."""
    f = build_filter()
    assert matches(f, {})
    assert matches(f, {"anything": 1, "else": "x"})
