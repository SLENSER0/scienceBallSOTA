"""[DE] Role → source-access clearance (§17.1/§19.3).

The clearance ladder decides which access levels a role may read, and
``filter_by_clearance`` drops any row above that ceiling so a disallowed source
never reaches the caller — «данные из запрещённого источника не отдаются».
"""

from __future__ import annotations

from kg_common.security.clearance import (
    allowed_access_levels,
    can_view,
    filter_by_clearance,
    principal_from,
)
from kg_common.security.source_access import Principal


def test_clearance_ladder() -> None:
    assert allowed_access_levels("external_partner") == frozenset({"public"})
    assert allowed_access_levels("researcher") == frozenset({"public", "internal"})
    assert allowed_access_levels("analyst") == frozenset({"public", "internal"})
    assert "restricted" in allowed_access_levels("curator")
    assert "restricted" in allowed_access_levels("admin")
    # fail-closed: an unknown role sees only public
    assert allowed_access_levels("stranger") == frozenset({"public"})


def test_can_view_by_level() -> None:
    # missing / public source → visible to everyone
    assert can_view("external_partner", None) is True
    assert can_view("external_partner", "public") is True
    # internal hidden from external_partner, visible to researcher+
    assert can_view("external_partner", "internal") is False
    assert can_view("researcher", "internal") is True
    # restricted only for curator/pm/admin
    assert can_view("researcher", "restricted") is False
    assert can_view("analyst", "restricted") is False
    assert can_view("curator", "restricted") is True
    assert can_view("admin", "commercial_secret") is True  # legacy top-tier synonym
    # an unknown, non-empty label is fail-closed (only full clearance)
    assert can_view("researcher", "top-secret") is False
    assert can_view("admin", "top-secret") is True


def test_filter_by_clearance_drops_disallowed_sources() -> None:
    rows = [
        {"id": "a", "confidentiality_level": "public"},
        {"id": "b", "confidentiality_level": "internal"},
        {"id": "c", "confidentiality_level": "restricted"},
        {"id": "d"},  # untagged → public
        {"id": "e", "access_level": "internal"},  # the other field name
    ]
    assert [r["id"] for r in filter_by_clearance("external_partner", rows)] == ["a", "d"]
    assert [r["id"] for r in filter_by_clearance("researcher", rows)] == ["a", "b", "d", "e"]
    assert [r["id"] for r in filter_by_clearance("admin", rows)] == ["a", "b", "c", "d", "e"]


def test_principal_from_bridges_source_acls() -> None:
    p = principal_from("u_alice", "researcher", ["lab_a", "lab_b"])
    assert isinstance(p, Principal)
    assert p.user_id == "u_alice"
    assert p.roles == frozenset({"researcher"})
    assert p.labs == frozenset({"lab_a", "lab_b"})
