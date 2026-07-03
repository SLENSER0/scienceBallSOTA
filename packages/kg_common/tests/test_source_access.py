"""Tests for source-level access decisions (§19.3 access policy)."""

from __future__ import annotations

from kg_common.security.source_access import (
    Principal,
    SourceAcl,
    can_access_source,
    filter_sources,
)


def _researcher() -> Principal:
    return Principal("u", frozenset({"researcher"}), frozenset())


def _admin() -> Principal:
    return Principal("admin_user", frozenset({"admin"}), frozenset())


def test_public_accessible_to_any_principal() -> None:
    acl = SourceAcl("s", "public", None, frozenset())
    assert can_access_source(_researcher(), acl) is True


def test_private_owner_accessible_but_not_other_user() -> None:
    acl = SourceAcl("s", "private", "u", frozenset())
    assert can_access_source(_researcher(), acl) is True
    other = Principal("v", frozenset({"researcher"}), frozenset())
    assert can_access_source(other, acl) is False


def test_admin_accesses_another_owners_private() -> None:
    acl = SourceAcl("s", "private", "u", frozenset())
    assert can_access_source(_admin(), acl) is True


def test_lab_restricted_accessible_on_intersecting_lab() -> None:
    acl = SourceAcl("s", "lab_restricted", "owner", frozenset({"A"}))
    principal = Principal("v", frozenset({"researcher"}), frozenset({"A"}))
    assert can_access_source(principal, acl) is True


def test_lab_restricted_denied_when_labs_disjoint() -> None:
    acl = SourceAcl("s", "lab_restricted", "owner", frozenset({"A"}))
    principal = Principal("v", frozenset({"researcher"}), frozenset({"B"}))
    assert can_access_source(principal, acl) is False


def test_owner_accesses_own_lab_restricted_with_empty_labs() -> None:
    acl = SourceAcl("s", "lab_restricted", "u", frozenset({"A"}))
    principal = Principal("u", frozenset({"researcher"}), frozenset())
    assert can_access_source(principal, acl) is True


def test_empty_policy_denied_to_non_admin_deny_by_default() -> None:
    acl = SourceAcl("s", "", None, frozenset())
    assert can_access_source(_researcher(), acl) is False


def test_unknown_policy_denied_to_non_admin_but_admin_allowed() -> None:
    acl = SourceAcl("s", "weird_mode", None, frozenset())
    assert can_access_source(_researcher(), acl) is False
    assert can_access_source(_admin(), acl) is True


def test_unknown_policy_owner_allowed() -> None:
    acl = SourceAcl("s", "weird_mode", "u", frozenset())
    assert can_access_source(_researcher(), acl) is True


def test_filter_sources_keeps_accessible_subset_in_order() -> None:
    principal = Principal("u", frozenset({"researcher"}), frozenset({"A"}))
    acls = (
        SourceAcl("s1", "public", None, frozenset()),
        SourceAcl("s2", "private", "v", frozenset()),  # denied
        SourceAcl("s3", "private", "u", frozenset()),  # owned
        SourceAcl("s4", "lab_restricted", "v", frozenset({"A"})),  # lab match
        SourceAcl("s5", "lab_restricted", "v", frozenset({"B"})),  # denied
        SourceAcl("s6", "", None, frozenset()),  # deny-by-default
    )
    result = filter_sources(principal, acls)
    assert [a.source_id for a in result] == ["s1", "s3", "s4"]


def test_filter_sources_empty_input() -> None:
    assert filter_sources(_researcher(), ()) == ()


def test_principal_as_dict_sorted() -> None:
    principal = Principal("u", frozenset({"researcher", "admin"}), frozenset({"B", "A"}))
    assert principal.as_dict() == {
        "user_id": "u",
        "roles": ["admin", "researcher"],
        "labs": ["A", "B"],
    }


def test_source_acl_as_dict_sorted() -> None:
    acl = SourceAcl("s", "lab_restricted", "u", frozenset({"B", "A"}))
    assert acl.as_dict() == {
        "source_id": "s",
        "access_policy": "lab_restricted",
        "owner_id": "u",
        "allowed_lab_ids": ["A", "B"],
    }


def test_dataclasses_are_frozen() -> None:
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        _researcher().user_id = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        SourceAcl("s", "public", None, frozenset()).source_id = "x"  # type: ignore[misc]
