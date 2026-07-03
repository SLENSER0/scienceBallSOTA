"""Тесты RBAC-ролей curation (§16.9): viewer/curator/admin и функция can()."""

from __future__ import annotations

from kg_common.storage.curation_rbac import (
    ADMIN_ACTIONS,
    CURATOR_ACTIONS,
    VIEWER_ACTIONS,
    AccessDecision,
    allowed_actions,
    can,
)


def test_viewer_cannot_merge() -> None:
    d = can("viewer", "merge")
    assert d.status == 403
    assert d.allowed is False
    assert d.role == "viewer"
    assert d.action == "merge"


def test_curator_can_correct() -> None:
    d = can("curator", "correct")
    assert d.allowed is True
    assert d.status == 200


def test_curator_cannot_merge() -> None:
    assert can("curator", "merge").status == 403
    assert can("curator", "merge").allowed is False


def test_admin_can_schema_change() -> None:
    d = can("admin", "schema_change")
    assert d.allowed is True
    assert d.status == 200


def test_anonymous_is_unauthorized() -> None:
    d = can("", "accept")
    assert d.status == 401
    assert d.allowed is False
    assert d.role == ""


def test_none_role_is_unauthorized() -> None:
    # type: ignore[arg-type] — граница: None трактуется как анонимность.
    assert can(None, "accept").status == 401  # type: ignore[arg-type]


def test_admin_has_merge_curator_does_not() -> None:
    assert "merge" in allowed_actions("admin")
    assert "merge" not in allowed_actions("curator")


def test_viewer_subset_of_curator() -> None:
    assert allowed_actions("viewer") <= allowed_actions("curator")
    assert allowed_actions("curator") <= allowed_actions("admin")


def test_viewer_is_read_only() -> None:
    assert allowed_actions("viewer") == {"read"}
    assert can("viewer", "read").allowed is True
    assert can("viewer", "accept").status == 403


def test_curator_full_action_set() -> None:
    expected = {
        "read",
        "accept",
        "reject",
        "correct",
        "alias_add",
        "mark_inferred",
        "manual_evidence",
        "annotate_gap",
        "mark_verified",
        "resolve",
    }
    assert allowed_actions("curator") == expected


def test_admin_structural_actions() -> None:
    for action in ("merge", "split", "schema_change", "revert", "assign"):
        assert can("admin", action).allowed is True
    # admin = curator + структурные / plus structural.
    structural = {"merge", "split", "schema_change", "revert", "assign"}
    assert allowed_actions("admin") == set(CURATOR_ACTIONS) | structural


def test_unknown_role_forbidden() -> None:
    d = can("robot", "read")
    assert d.status == 403
    assert d.allowed is False
    assert allowed_actions("robot") == set()


def test_role_normalized_case_and_whitespace() -> None:
    d = can("  ADMIN ", "merge")
    assert d.allowed is True
    assert d.role == "admin"
    assert allowed_actions("  Curator ") == set(CURATOR_ACTIONS)


def test_as_dict_echoes_action() -> None:
    d = can("curator", "correct")
    payload = d.as_dict()
    assert payload["action"] == "correct"
    assert payload == {
        "allowed": True,
        "status": 200,
        "role": "curator",
        "action": "correct",
    }


def test_as_dict_echoes_forbidden_action() -> None:
    assert can("viewer", "merge").as_dict()["action"] == "merge"
    assert can("", "accept").as_dict()["action"] == "accept"


def test_decision_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    d = AccessDecision(allowed=True, status=200, role="admin", action="merge")
    with pytest.raises(FrozenInstanceError):
        d.allowed = False  # type: ignore[misc]


def test_constant_maps_hierarchy() -> None:
    assert VIEWER_ACTIONS < CURATOR_ACTIONS < ADMIN_ACTIONS
    assert isinstance(ADMIN_ACTIONS, frozenset)
