"""Tests for multi-role effective permissions & RBAC invariants (§19.1)."""

from __future__ import annotations

from kg_common.security.effective_permissions import (
    ROLE_MATRIX,
    RoleGrant,
    effective_permissions,
    every_permission_assigned,
    has_permission,
    role_grant,
    viewer_has_no_write,
    write_scopes,
)


def test_role_grant_as_dict_sorts_permissions() -> None:
    grant = RoleGrant(role="viewer", permissions=frozenset({"graph:read", "chat:read"}))
    assert grant.as_dict() == {
        "role": "viewer",
        "permissions": ["chat:read", "graph:read"],
    }


def test_role_grant_unknown_role_is_empty() -> None:
    grant = role_grant("no_such_role")
    assert grant.role == "no_such_role"
    assert grant.permissions == frozenset()


def test_viewer_contains_no_write_scope() -> None:
    # Assertion (1): viewer's effective set intersects no write scope.
    viewer = effective_permissions(["viewer"])
    assert viewer & write_scopes() == frozenset()


def test_admin_superset_of_researcher() -> None:
    # Assertion (2): admin grants everything researcher grants (and more).
    admin = effective_permissions(["admin"])
    researcher = effective_permissions(["researcher"])
    assert admin >= researcher
    assert admin > researcher


def test_union_equals_component_union() -> None:
    # Assertion (3): researcher+viewer union equals the two role sets unioned.
    combined = effective_permissions(["researcher", "viewer"])
    expected = ROLE_MATRIX["researcher"] | ROLE_MATRIX["viewer"]
    assert combined == expected


def test_unknown_role_ignored_in_union() -> None:
    # Assertion (4): an unknown role adds nothing to the union.
    with_unknown = effective_permissions(["researcher", "ghost_role"])
    without_unknown = effective_permissions(["researcher"])
    assert with_unknown == without_unknown


def test_every_permission_assigned() -> None:
    # Assertion (5): each scope belongs to at least one role.
    assert every_permission_assigned() is True


def test_viewer_has_no_write_invariant() -> None:
    # Assertion (6): the dedicated invariant holds for viewer.
    assert viewer_has_no_write() is True


def test_has_permission_viewer_read_yes_merge_no() -> None:
    # Assertion (7): viewer can read chat but cannot merge entities.
    assert has_permission(["viewer"], "chat:read") is True
    assert has_permission(["viewer"], "entities:merge") is False


def test_empty_roles_grant_nothing() -> None:
    assert effective_permissions([]) == frozenset()
    assert has_permission([], "chat:read") is False


def test_write_scopes_are_mutating_only() -> None:
    scopes = write_scopes()
    assert scopes  # non-empty
    assert "entities:merge" in scopes
    assert "sources:upload" in scopes
    assert "review:approve" in scopes
    # read scopes never appear in the write set.
    assert "chat:read" not in scopes
    assert "graph:read" not in scopes


def test_ingest_operator_can_ingest_but_not_merge() -> None:
    assert has_permission(["ingest_operator"], "sources:ingest") is True
    assert has_permission(["ingest_operator"], "entities:merge") is False


def test_multi_role_grants_stacked_permissions() -> None:
    # viewer alone cannot write graph; adding service grants graph:write.
    assert has_permission(["viewer"], "graph:write") is False
    assert has_permission(["viewer", "service"], "graph:write") is True
