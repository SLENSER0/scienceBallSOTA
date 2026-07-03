"""Tests for sort-parameter parsing and stable ordering (§14.16).

Hermetic and dependency-free. Every assertion is a concrete hand-computed
value: the ``asc`` default for a bare field, an explicit ``desc``, multi-field
parsing, rejection of unknown fields / bad directions / malformed tokens, the
empty-string short-circuit, plus :func:`apply_sort` ascending, descending,
multi-key and tie-stability behaviour.
"""

from __future__ import annotations

import pytest
from api_gateway.sort_params import SortKey, apply_sort, parse_sort

ALLOWED = {"name", "created", "score"}


def test_single_field_defaults_to_asc() -> None:
    assert parse_sort("name", ALLOWED) == [SortKey("name", "asc")]


def test_explicit_desc() -> None:
    assert parse_sort("name:desc", ALLOWED) == [SortKey("name", "desc")]


def test_explicit_asc() -> None:
    assert parse_sort("created:asc", ALLOWED) == [SortKey("created", "asc")]


def test_multi_field_preserves_order() -> None:
    assert parse_sort("name:desc,created:asc", ALLOWED) == [
        SortKey("name", "desc"),
        SortKey("created", "asc"),
    ]


def test_direction_is_case_insensitive() -> None:
    assert parse_sort("name:DESC", ALLOWED) == [SortKey("name", "desc")]


def test_whitespace_around_tokens_is_stripped() -> None:
    assert parse_sort(" name : desc , created ", ALLOWED) == [
        SortKey("name", "desc"),
        SortKey("created", "asc"),
    ]


def test_empty_sort_returns_empty_list() -> None:
    assert parse_sort("", ALLOWED) == []


def test_whitespace_only_sort_returns_empty_list() -> None:
    assert parse_sort("   ", ALLOWED) == []


def test_unknown_field_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_sort("bogus:asc", ALLOWED)


def test_bad_direction_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_sort("name:sideways", ALLOWED)


def test_empty_token_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_sort("name,,created", ALLOWED)


def test_too_many_colons_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_sort("name:asc:extra", ALLOWED)


def test_missing_field_before_colon_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_sort(":asc", ALLOWED)


def test_sort_key_as_dict_shape() -> None:
    assert SortKey("name", "desc").as_dict() == {"field": "name", "direction": "desc"}


def test_apply_sort_orders_rows_ascending() -> None:
    rows = [{"name": "c"}, {"name": "a"}, {"name": "b"}]
    ordered = apply_sort(rows, parse_sort("name", ALLOWED))
    assert [r["name"] for r in ordered] == ["a", "b", "c"]


def test_apply_sort_orders_rows_descending() -> None:
    rows = [{"score": 1}, {"score": 3}, {"score": 2}]
    ordered = apply_sort(rows, parse_sort("score:desc", ALLOWED))
    assert [r["score"] for r in ordered] == [3, 2, 1]


def test_apply_sort_multi_key() -> None:
    rows = [
        {"name": "b", "score": 1},
        {"name": "a", "score": 2},
        {"name": "a", "score": 1},
        {"name": "b", "score": 2},
    ]
    ordered = apply_sort(rows, parse_sort("name:asc,score:desc", ALLOWED))
    assert [(r["name"], r["score"]) for r in ordered] == [
        ("a", 2),
        ("a", 1),
        ("b", 2),
        ("b", 1),
    ]


def test_apply_sort_is_stable_on_ties() -> None:
    # Equal sort keys must keep their input relative order (id tie-breaker).
    rows = [
        {"name": "a", "id": 1},
        {"name": "a", "id": 2},
        {"name": "a", "id": 3},
    ]
    ordered = apply_sort(rows, parse_sort("name:asc", ALLOWED))
    assert [r["id"] for r in ordered] == [1, 2, 3]


def test_apply_sort_empty_sort_returns_input_copy() -> None:
    rows = [{"name": "b"}, {"name": "a"}]
    ordered = apply_sort(rows, parse_sort("", ALLOWED))
    assert ordered == rows
    assert ordered is not rows  # shallow copy, not the same list object


def test_apply_sort_stable_under_descending_ties() -> None:
    # reverse=True must also preserve input order for equal keys.
    rows = [
        {"name": "a", "id": 1},
        {"name": "a", "id": 2},
        {"name": "a", "id": 3},
    ]
    ordered = apply_sort(rows, parse_sort("name:desc", ALLOWED))
    assert [r["id"] for r in ordered] == [1, 2, 3]
