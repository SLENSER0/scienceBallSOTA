"""Entity crosswalk → external-id to canonical-id mapping (§10.3)."""

from __future__ import annotations

import pytest

from kg_common.storage.entity_mapping import Crosswalk, EntityMapping


@pytest.fixture
def xw() -> EntityMapping:
    m = EntityMapping("sqlite:///:memory:")
    m.migrate()
    return m


def test_map_and_resolve(xw: EntityMapping) -> None:
    xw.map_id("0000-0002-1825-0097", "orcid", "person:ivanov")
    assert xw.resolve("0000-0002-1825-0097", "orcid") == "person:ivanov"


def test_idempotent_remap_updates_canonical(xw: EntityMapping) -> None:
    xw.map_id("PMID:123", "pubmed", "doc:old")
    xw.map_id("PMID:123", "pubmed", "doc:new")  # re-point same external id
    # no duplicate row, canonical refreshed to the latest target
    rows = xw.external_ids_for("doc:new")
    assert len(rows) == 1
    assert xw.resolve("PMID:123", "pubmed") == "doc:new"
    assert xw.external_ids_for("doc:old") == []  # old target no longer referenced


def test_reverse_lookup_external_ids_for(xw: EntityMapping) -> None:
    xw.map_id("0000-0002-1825-0097", "orcid", "person:ivanov")
    xw.map_id("ivanov-2020", "lims", "person:ivanov")
    xw.map_id("someone-else", "lims", "person:petrov")
    rows = xw.external_ids_for("person:ivanov")
    # ordered by (source_system, external_id): lims before orcid
    assert [(r.source_system, r.external_id) for r in rows] == [
        ("lims", "ivanov-2020"),
        ("orcid", "0000-0002-1825-0097"),
    ]


def test_same_external_id_across_systems_is_distinct(xw: EntityMapping) -> None:
    # the same numeric string means different entities in different systems
    xw.map_id("123", "pubmed", "doc:paper")
    xw.map_id("123", "lims", "sample:vial")  # UNIQUE(external_id, source_system)
    assert xw.resolve("123", "pubmed") == "doc:paper"
    assert xw.resolve("123", "lims") == "sample:vial"
    assert len(xw.external_ids_for("doc:paper")) == 1
    assert len(xw.external_ids_for("sample:vial")) == 1


def test_remove(xw: EntityMapping) -> None:
    xw.map_id("0000-0002-1825-0097", "orcid", "person:ivanov")
    xw.map_id("ivanov-2020", "lims", "person:ivanov")
    xw.remove("0000-0002-1825-0097", "orcid")
    remaining = xw.external_ids_for("person:ivanov")
    assert len(remaining) == 1 and remaining[0].source_system == "lims"
    assert xw.resolve("0000-0002-1825-0097", "orcid") is None


def test_unknown_resolves_to_none(xw: EntityMapping) -> None:
    assert xw.resolve("missing", "orcid") is None
    assert xw.external_ids_for("person:nobody") == []
    xw.remove("missing", "orcid")  # graceful no-op, must not raise


def test_crosswalk_as_dict() -> None:
    c = Crosswalk("0000-0002-1825-0097", "orcid", "person:ivanov")
    assert c.as_dict() == {
        "external_id": "0000-0002-1825-0097",
        "source_system": "orcid",
        "canonical_id": "person:ivanov",
    }
