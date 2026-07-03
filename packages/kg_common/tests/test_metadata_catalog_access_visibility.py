"""Tests for catalog visibility by role and access tag — тесты §10.11."""

from __future__ import annotations

from kg_common.metadata.catalog_access_visibility import (
    ACCESS_RANK,
    ROLE_MAX,
    VisibilityDecision,
    can_see,
    decide,
    max_access_for,
    visible_sources,
)


def test_access_rank_ordering() -> None:
    assert ACCESS_RANK == {"public": 0, "internal": 1, "restricted": 2}
    assert ACCESS_RANK["public"] < ACCESS_RANK["internal"] < ACCESS_RANK["restricted"]


def test_role_max_table() -> None:
    assert ROLE_MAX["admin"] == "restricted"
    assert ROLE_MAX["curator"] == "restricted"
    assert ROLE_MAX["member"] == "internal"
    assert ROLE_MAX["external_partner"] == "public"


def test_max_access_for_known_roles() -> None:
    assert max_access_for("admin") == "restricted"
    assert max_access_for("member") == "internal"
    assert max_access_for("external_partner") == "public"


def test_max_access_for_unknown_role_fails_closed() -> None:
    # Unknown role → public (least privileged).
    assert max_access_for("unknown_role") == "public"
    assert max_access_for("") == "public"


def test_admin_sees_restricted() -> None:
    assert can_see("admin", "restricted") is True


def test_member_cannot_see_restricted_but_sees_internal() -> None:
    assert can_see("member", "restricted") is False
    assert can_see("member", "internal") is True
    assert can_see("member", "public") is True


def test_external_partner_only_public() -> None:
    assert can_see("external_partner", "internal") is False
    assert can_see("external_partner", "public") is True
    assert can_see("external_partner", "restricted") is False


def test_unknown_role_fails_closed() -> None:
    assert can_see("unknown_role", "internal") is False
    assert can_see("unknown_role", "public") is True


def test_unknown_access_fails_closed() -> None:
    # A weird/malformed access is treated as restricted → hidden by default.
    assert can_see("admin", "weird") is False
    assert can_see("curator", "weird") is False
    assert can_see("member", "weird") is False


def test_decide_returns_frozen_record() -> None:
    d = decide("curator", "restricted")
    assert isinstance(d, VisibilityDecision)
    assert d.role == "curator"
    assert d.access == "restricted"
    assert d.visible is True
    assert d.as_dict() == {"role": "curator", "access": "restricted", "visible": True}


def test_decide_hidden_case() -> None:
    d = decide("external_partner", "internal")
    assert d.visible is False
    assert d.as_dict() == {
        "role": "external_partner",
        "access": "internal",
        "visible": False,
    }


def test_visibility_decision_is_frozen() -> None:
    d = VisibilityDecision(role="admin", access="public", visible=True)
    try:
        d.visible = False  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover
        raise AssertionError("VisibilityDecision must be frozen")


def test_visible_sources_filters_and_preserves_order() -> None:
    cards = [
        {"id": "pub", "access": "public"},
        {"id": "int", "access": "internal"},
        {"id": "res", "access": "restricted"},
    ]
    got = visible_sources("member", cards)
    # Member sees public + internal, in original order; restricted dropped.
    assert [c["id"] for c in got] == ["pub", "int"]
    assert got == cards[:2]


def test_visible_sources_external_partner_only_public() -> None:
    cards = [
        {"id": "int", "access": "internal"},
        {"id": "pub", "access": "public"},
        {"id": "res", "access": "restricted"},
    ]
    got = visible_sources("external_partner", cards)
    assert [c["id"] for c in got] == ["pub"]


def test_visible_sources_admin_sees_all() -> None:
    cards = [
        {"id": "a", "access": "public"},
        {"id": "b", "access": "internal"},
        {"id": "c", "access": "restricted"},
    ]
    assert visible_sources("admin", cards) == cards


def test_visible_sources_missing_access_fails_closed() -> None:
    # A card without an 'access' key → None → treated as restricted → hidden.
    cards = [{"id": "x"}, {"id": "y", "access": "public"}]
    assert [c["id"] for c in visible_sources("member", cards)] == ["y"]
