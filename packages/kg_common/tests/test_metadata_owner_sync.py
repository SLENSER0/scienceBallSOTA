"""§10.6 tests — owner sync (Person/Team/Lab → CorpUser/CorpGroup).

RU: Проверки маппинга владельцев и рёбер членства. EN: Owner-mapping and
membership-edge checks. Hand-verifiable, no I/O.
"""

from __future__ import annotations

import pytest

from kg_common.metadata.owner_sync import (
    CorpPrincipal,
    lab_to_corpgroup,
    membership_edges,
    person_to_corpuser,
    team_to_corpgroup,
)


def test_person_to_corpuser_lowercases_urn() -> None:
    principal = person_to_corpuser({"id": "A.Smith"})
    assert principal.urn == "urn:li:corpuser:a.smith"
    assert principal.kind == "user"


def test_person_source_id_preserves_original_case() -> None:
    assert person_to_corpuser({"id": "X"}).as_dict()["source_id"] == "X"


def test_person_display_name_falls_back_to_id() -> None:
    assert person_to_corpuser({"id": "A.Smith"}).display_name == "A.Smith"


def test_person_display_name_uses_name_when_given() -> None:
    assert person_to_corpuser({"id": "u1", "name": "Alice"}).display_name == "Alice"


def test_empty_person_id_raises() -> None:
    with pytest.raises(ValueError):
        person_to_corpuser({"id": ""})


def test_missing_person_id_raises() -> None:
    with pytest.raises(ValueError):
        person_to_corpuser({})


def test_lab_to_corpgroup_urn() -> None:
    principal = lab_to_corpgroup({"id": "lab1"})
    assert principal.urn == "urn:li:corpGroup:lab1"
    assert principal.kind == "group"


def test_team_to_corpgroup_display_name() -> None:
    principal = team_to_corpgroup({"id": "t", "name": "Team"})
    assert principal.display_name == "Team"
    assert principal.urn == "urn:li:corpGroup:t"


def test_group_urn_preserves_case() -> None:
    assert lab_to_corpgroup({"id": "LabX"}).urn == "urn:li:corpGroup:LabX"


def test_empty_group_id_raises() -> None:
    with pytest.raises(ValueError):
        team_to_corpgroup({"id": ""})


def test_membership_edges_sorted_and_deduped() -> None:
    edges = membership_edges({"id": "u1"}, ["g2", "g1", "g1"])
    assert edges == [
        ("urn:li:corpuser:u1", "urn:li:corpGroup:g1"),
        ("urn:li:corpuser:u1", "urn:li:corpGroup:g2"),
    ]


def test_membership_edges_empty_groups() -> None:
    assert membership_edges({"id": "u1"}, []) == []


def test_membership_edges_uses_lowercased_user_urn() -> None:
    edges = membership_edges({"id": "A.Smith"}, ["g1"])
    assert edges == [("urn:li:corpuser:a.smith", "urn:li:corpGroup:g1")]


def test_membership_edges_missing_id_raises() -> None:
    with pytest.raises(ValueError):
        membership_edges({}, ["g1"])


def test_corpprincipal_is_frozen() -> None:
    principal = person_to_corpuser({"id": "u1"})
    with pytest.raises((AttributeError, TypeError)):
        principal.urn = "other"  # type: ignore[misc]


def test_as_dict_round_trip() -> None:
    principal = person_to_corpuser({"id": "u1", "name": "Alice"})
    assert principal.as_dict() == {
        "kind": "user",
        "urn": "urn:li:corpuser:u1",
        "display_name": "Alice",
        "source_id": "u1",
    }
    assert isinstance(principal, CorpPrincipal)
