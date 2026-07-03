"""Tests for auto-labelling communities from their top member entities (§11.12).

Builds a small deterministic Kuzu store with two communities whose members carry known
``degree`` centralities, then hand-checks that the RU label is built from the highest-degree
member names, that ``size`` counts members (excluding the Finding summary artifact), that an
unknown community yields an empty label, that ``label_all`` returns one label per community,
that the ``top`` cap bounds the top entities, and the ``as_dict`` shape/copy contract.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.community_labels import (
    CommunityLabel,
    label_all_communities,
    label_community,
)
from kg_retrievers.graph_store import KuzuGraphStore

# Two communities: A (4 metal entities) and B (2 water-treatment entities).
_CID_A = 1
_CID_B = 2

# Community A members ranked by degree (most-connected first): Сталь > Медь > Железо > Никель.
_A_BY_DEGREE = ["Сталь", "Медь", "Железо", "Никель"]
# Community B members ranked by degree: Вода > Осмос.
_B_BY_DEGREE = ["Вода", "Осмос"]


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    # -- community A: four metal entities with distinct degrees --
    s.upsert_node("a-steel", "Material", name="Сталь", community_id=_CID_A, degree=12)
    s.upsert_node("a-copper", "Material", name="Медь", community_id=_CID_A, degree=7)
    s.upsert_node("a-iron", "Material", name="Железо", community_id=_CID_A, degree=4)
    s.upsert_node("a-nickel", "Material", name="Никель", community_id=_CID_A, degree=1)
    # community-summary artifact (Finding) — must NOT count as a member or a top entity
    s.upsert_node("find-a", "Finding", name="Community summary #1", community_id=_CID_A, degree=99)
    # -- community B: two water-treatment entities --
    s.upsert_node("b-water", "Material", name="Вода", community_id=_CID_B, degree=9)
    s.upsert_node("b-osmo", "Method", name="Осмос", community_id=_CID_B, degree=3)
    yield s
    s.close()


def test_label_uses_top_entity_names(store: KuzuGraphStore) -> None:
    lab = label_community(store, _CID_A)
    # top entities are the highest-degree members, most-connected first
    assert lab.top_entities == _A_BY_DEGREE[:3]  # Сталь, Медь, Железо
    # the RU label is built from exactly those names, in order
    assert lab.label == "Кластер: Сталь, Медь, Железо"
    for name in lab.top_entities:
        assert name in lab.label
    assert lab.community_id == _CID_A


def test_size_counts_members(store: KuzuGraphStore) -> None:
    # size counts the entity members only — the Finding summary artifact is excluded
    assert label_community(store, _CID_A).size == 4
    assert label_community(store, _CID_B).size == 2


def test_unknown_community_empty_label(store: KuzuGraphStore) -> None:
    lab = label_community(store, 999)
    assert lab.label == ""
    assert lab.top_entities == []
    assert lab.size == 0
    assert lab.community_id == 999


def test_label_all_returns_one_per_community(store: KuzuGraphStore) -> None:
    labels = label_all_communities(store)
    assert isinstance(labels, list)
    # exactly one label per community, in ascending community_id order
    assert [lab.community_id for lab in labels] == [_CID_A, _CID_B]
    assert labels[0].top_entities == _A_BY_DEGREE[:3]
    assert labels[1].top_entities == _B_BY_DEGREE  # only two members -> both surface
    # every community gets a non-empty label built from its members
    assert all(lab.label for lab in labels)


def test_top_cap(store: KuzuGraphStore) -> None:
    lab = label_community(store, _CID_A, top=2)
    assert lab.top_entities == _A_BY_DEGREE[:2]  # Сталь, Медь
    assert lab.label == "Кластер: Сталь, Медь"
    # the cap does not change the member count
    assert lab.size == 4
    # lower-degree members are excluded from both the list and the label
    assert "Железо" not in lab.label
    assert "Никель" not in lab.label
    # a cap larger than the membership is harmless — it just returns every member
    big = label_community(store, _CID_B, top=5)
    assert big.top_entities == _B_BY_DEGREE
    assert big.size == 2


def test_as_dict(store: KuzuGraphStore) -> None:
    lab = label_community(store, _CID_A, top=3)
    d = lab.as_dict()
    assert set(d) == {"community_id", "label", "top_entities", "size"}
    assert d["community_id"] == _CID_A
    assert d["label"] == lab.label
    assert d["top_entities"] == _A_BY_DEGREE[:3]
    assert d["size"] == 4
    # as_dict returns a copy — mutating it must not corrupt the frozen record
    d["top_entities"].append("tampered")
    assert "tampered" not in lab.top_entities


def test_label_all_forwards_top_cap(store: KuzuGraphStore) -> None:
    labels = label_all_communities(store, top=1)
    # each community is labelled with only its single most-connected member
    assert [lab.top_entities for lab in labels] == [["Сталь"], ["Вода"]]
    assert labels[0].label == "Кластер: Сталь"
    # sizes are independent of the top cap
    assert [lab.size for lab in labels] == [4, 2]


def test_frozen_label_is_immutable() -> None:
    lab = CommunityLabel(community_id=7, label="Кластер: X", top_entities=["X"], size=1)
    with pytest.raises(AttributeError):
        lab.label = "changed"  # type: ignore[misc]
