"""Tests for shared pagination / validation schemas (§14.2).

Hermetic and dependency-free: exercises :class:`PageParams` bounds, the
:func:`build_paginated` envelope shape (must match the router's existing
``{total, count, limit, offset, items}`` contract) and :func:`parse_sort`
whitelisting. Every assertion checks a concrete, hand-computed value.
"""

from __future__ import annotations

import pytest
from api_gateway.schemas_common import PageParams, build_paginated, parse_sort
from pydantic import ValidationError

_ALLOWED = {"name", "domain", "created_at"}


def test_page_params_rejects_limit_zero() -> None:
    with pytest.raises(ValidationError):
        PageParams(limit=0)


def test_page_params_rejects_limit_over_max() -> None:
    with pytest.raises(ValidationError):
        PageParams(limit=201)


def test_page_params_accepts_limit_boundary_200() -> None:
    assert PageParams(limit=200).limit == 200


def test_page_params_rejects_negative_offset() -> None:
    with pytest.raises(ValidationError):
        PageParams(offset=-1)


def test_page_params_accepts_offset_zero() -> None:
    assert PageParams(offset=0).offset == 0


def test_page_params_defaults() -> None:
    p = PageParams()
    assert (p.limit, p.offset, p.sort) == (50, 0, None)


def test_build_paginated_shape_and_count() -> None:
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    env = build_paginated(items, total=42, params=PageParams(limit=3, offset=6))
    assert env == {
        "total": 42,
        "count": 3,
        "limit": 3,
        "offset": 6,
        "items": items,
    }
    assert list(env.keys()) == ["total", "count", "limit", "offset", "items"]


def test_build_paginated_total_independent_of_count() -> None:
    # Page of 2 items drawn from a matched set of 100 → count!=total.
    env = build_paginated([{"id": "x"}, {"id": "y"}], total=100, params=PageParams())
    assert env["count"] == 2
    assert env["total"] == 100
    assert env["count"] != env["total"]


def test_build_paginated_empty_page() -> None:
    env = build_paginated([], total=5, params=PageParams(offset=10))
    assert env["count"] == 0
    assert env["total"] == 5
    assert env["items"] == []


def test_parse_sort_splits_field_and_direction() -> None:
    assert parse_sort("name:desc", _ALLOWED) == ("name", "desc")


def test_parse_sort_defaults_direction_to_asc() -> None:
    assert parse_sort("domain", _ALLOWED) == ("domain", "asc")


def test_parse_sort_rejects_unknown_field() -> None:
    with pytest.raises(ValueError):
        parse_sort("bogus:asc", _ALLOWED)


def test_parse_sort_rejects_unknown_direction() -> None:
    with pytest.raises(ValueError):
        parse_sort("name:sideways", _ALLOWED)


def test_parse_sort_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_sort(None, _ALLOWED)
