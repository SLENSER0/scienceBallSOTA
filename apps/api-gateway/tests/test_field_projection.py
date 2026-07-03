"""Tests for the §14.2 ``?fields=`` sparse fieldset projection.

Проверяет разбор spec (include/exclude, обрезка пробелов, ``None``) и проекцию
отображения по маске: только include-ключи, отбрасывание exclude-ключей и
identity-копия для пустой маски (§14.2).
"""

from __future__ import annotations

from api_gateway.field_projection import (
    FieldMask,
    parse_fields,
    project,
)


def test_parse_include_tokens() -> None:
    """(1) bare comma tokens become the include set."""
    assert parse_fields("id,name").include == frozenset({"id", "name"})


def test_parse_exclude_token() -> None:
    """(2) a ``-``-prefixed token becomes an exclude."""
    assert parse_fields("-secret").exclude == frozenset({"secret"})


def test_parse_strips_whitespace() -> None:
    """(3) surrounding whitespace around tokens is stripped."""
    assert parse_fields("id, name ").include == frozenset({"id", "name"})


def test_parse_none_is_empty_mask() -> None:
    """(4) a ``None`` spec yields an empty mask (both sets empty)."""
    mask = parse_fields(None)
    assert mask.include == frozenset()
    assert mask.exclude == frozenset()


def test_project_keeps_only_includes() -> None:
    """(5) a non-empty include keeps only listed present keys."""
    obj = {"id": 1, "name": "x", "z": 2}
    assert project(obj, parse_fields("id,name")) == {"id": 1, "name": "x"}


def test_project_drops_excludes() -> None:
    """(6) with no includes, exclude keys are dropped."""
    assert project({"id": 1, "secret": 2}, parse_fields("-secret")) == {"id": 1}


def test_project_identity_for_empty_mask() -> None:
    """(7) an empty mask returns an identity copy of the object."""
    assert project({"id": 1}, parse_fields(None)) == {"id": 1}


def test_as_dict_lists_includes() -> None:
    """(8) ``as_dict()['include']`` reports the include keys."""
    assert "id" in parse_fields("id,name").as_dict()["include"]


def test_field_mask_is_frozen() -> None:
    """(9) :class:`FieldMask` is frozen and hashable (shareable mask)."""
    mask = FieldMask(include=frozenset({"id"}), exclude=frozenset())
    assert hash(mask) == hash(FieldMask(include=frozenset({"id"}), exclude=frozenset()))


def test_project_include_ignores_missing_keys() -> None:
    """(10) include of an absent key does not fabricate it in the result."""
    assert project({"id": 1}, parse_fields("id,ghost")) == {"id": 1}


def test_project_returns_plain_dict_copy() -> None:
    """(11) identity projection is a distinct dict, not the same object."""
    src = {"id": 1}
    out = project(src, parse_fields(None))
    assert out == src
    assert out is not src


def test_include_wins_over_exclude() -> None:
    """(12) when include is non-empty it takes precedence over exclude."""
    mask = parse_fields("id,-id")
    assert project({"id": 1, "name": "x"}, mask) == {"id": 1}
