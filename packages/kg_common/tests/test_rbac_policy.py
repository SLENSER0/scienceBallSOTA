"""Tests for the RBAC policy — тесты политики доступа (§19.12)."""

from __future__ import annotations

import pytest

from kg_common.rbac_policy import (
    ACTIONS,
    RESTRICTED_FIELDS,
    ROLE_PERMISSIONS,
    AccessDecision,
    can,
    decide,
    require,
    visible_fields,
)


def test_admin_has_every_action() -> None:
    """admin holds the whole action universe — админ имеет все права."""
    assert ROLE_PERMISSIONS["admin"] == ACTIONS
    for action in ACTIONS:
        assert can("admin", action) is True


def test_curator_may_merge_but_not_admin() -> None:
    """curator can merge/curate yet cannot administer or delete."""
    assert can("curator", "merge") is True
    assert can("curator", "curate") is True
    assert can("curator", "write") is True
    assert can("curator", "admin") is False
    assert can("curator", "delete") is False


def test_researcher_reads_and_writes_not_merge() -> None:
    """researcher reads/writes but cannot merge entities."""
    assert can("researcher", "read") is True
    assert can("researcher", "write") is True
    assert can("researcher", "merge") is False
    assert can("researcher", "admin") is False


def test_analyst_is_read_only_analytics() -> None:
    """analyst may read and export only — только чтение."""
    assert can("analyst", "read") is True
    assert can("analyst", "export") is True
    assert can("analyst", "write") is False
    assert can("analyst", "merge") is False


def test_external_partner_restricted_to_read() -> None:
    """external_partner may only read — внешний партнёр ограничен."""
    assert can("external_partner", "read") is True
    assert can("external_partner", "write") is False
    assert can("external_partner", "export") is False
    assert can("external_partner", "merge") is False


def test_can_returns_plain_bool() -> None:
    """can() returns a real bool, not a truthy set membership object."""
    result = can("researcher", "read")
    assert result is True
    assert isinstance(result, bool)
    assert can("researcher", "merge") is False


def test_require_allows_permitted_and_raises_denied() -> None:
    """require() is silent when allowed and raises PermissionError otherwise."""
    assert require("curator", "merge") is None
    with pytest.raises(PermissionError, match="researcher"):
        require("researcher", "merge")


def test_unknown_role_is_fail_closed() -> None:
    """An unknown role has no permissions and require() raises — fail-closed."""
    assert can("ghost", "read") is False
    assert can("ghost", "admin") is False
    with pytest.raises(PermissionError, match="ghost"):
        require("ghost", "read")


def test_unknown_action_is_denied() -> None:
    """An action outside the universe is denied even for admin."""
    assert can("admin", "launch_missiles") is False
    with pytest.raises(PermissionError):
        require("admin", "launch_missiles")


def test_visible_fields_hides_restricted_for_external() -> None:
    """external_partner sees no restricted fields; privileged roles see them."""
    assert visible_fields("external_partner") == set()
    assert visible_fields("curator") == set(RESTRICTED_FIELDS)
    assert visible_fields("admin") == set(RESTRICTED_FIELDS)


def test_visible_fields_projects_concrete_record() -> None:
    """visible_fields filters a concrete field set for external partners."""
    record = {"name", "value", "internal_notes", "provenance"}
    assert visible_fields("external_partner", record) == {"name", "value"}
    assert visible_fields("analyst", record) == record


def test_visible_fields_unknown_role_fail_closed() -> None:
    """An unknown role is treated as external and loses restricted fields."""
    record = {"name", "acl"}
    assert visible_fields("ghost", record) == {"name"}


def test_decide_builds_access_decision() -> None:
    """decide() returns a frozen AccessDecision with an as_dict() view."""
    d = decide("analyst", "read")
    assert isinstance(d, AccessDecision)
    assert d.allowed is True
    assert d.as_dict() == {"role": "analyst", "action": "read", "allowed": True}
    denied = decide("analyst", "delete")
    assert denied.allowed is False


def test_access_decision_is_frozen() -> None:
    """AccessDecision is immutable — заморожено."""
    d = decide("admin", "admin")
    with pytest.raises(AttributeError):
        d.allowed = False  # type: ignore[misc]
