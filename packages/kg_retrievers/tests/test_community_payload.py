"""Tests for the GraphRAG community-report payload schema (§11.5 / §9.8).

Builds a small deterministic Kuzu store with one materials/property community backed
by two source documents (via SUPPORTED_BY → Evidence), then hand-checks the assembled
§9.8 payload, the material/property split, the traced doc_ids, the search filters and
the as_dict/from_dict round-trip.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.community_payload import (
    PAYLOAD_KEYS,
    CommunityReportPayload,
    build_payload,
    search_payloads,
)
from kg_retrievers.graph_store import KuzuGraphStore

# Fixed build metadata (§9.8) — always supplied by the caller, never a live clock.
_BUILD_ID = "build-2026-07-03"
_BUILD_VERSION = "v1.2.0"
_CREATED_AT = "2026-07-03T00:00:00Z"

_MAIN = 5  # community with members + provenance
_EMPTY = 7  # community with no members

# Expected §9.8 keys — the exact set required by the acceptance criteria.
_EXPECTED_KEYS = {
    "community_id",
    "level",
    "title",
    "rank",
    "summary",
    "findings",
    "entity_ids",
    "material_ids",
    "property_ids",
    "doc_ids",
    "build_id",
    "build_version",
    "created_at",
}


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    # -- community 5 members: 2 materials, 1 property, 1 technology solution --
    s.upsert_node("mat-steel", "Material", name="Сталь", community_id=_MAIN)
    s.upsert_node("mat-copper", "Material", name="Медь", community_id=_MAIN)
    s.upsert_node("prop-hardness", "Property", name="Твёрдость", community_id=_MAIN)
    s.upsert_node("tech-quench", "TechnologySolution", name="Закалка", community_id=_MAIN)
    # -- provenance: Evidence nodes carrying source doc_ids --
    s.upsert_node("ev-a", "Evidence", text="steel HV up", doc_id="paperA.pdf")
    s.upsert_node("ev-b", "Evidence", text="quench effect", doc_id="paperB.pdf")
    s.upsert_node("paper-b", "Paper", name="Quench study")
    # community summary artifact (Finding) with optional level/rank custom props
    s.upsert_node(
        "find-5",
        "Finding",
        name="Cluster #5",
        text="Steel and copper hardness cluster.",
        community_id=_MAIN,
        level=1,
        rank=4.0,
    )
    # SUPPORTED_BY: direct Evidence target, and Paper target carrying evidence_ids
    s.upsert_edge("mat-steel", "ev-a", "SUPPORTED_BY", confidence=0.9)
    s.upsert_edge("tech-quench", "paper-b", "SUPPORTED_BY", confidence=0.8, evidence_ids=["ev-b"])
    yield s
    s.close()


def test_payload_has_all_98_keys(store: KuzuGraphStore) -> None:
    payload = build_payload(
        store, _MAIN, build_id=_BUILD_ID, build_version=_BUILD_VERSION, created_at=_CREATED_AT
    )
    d = payload.as_dict()
    assert set(d) == _EXPECTED_KEYS
    assert set(d) == set(PAYLOAD_KEYS)
    # build metadata is threaded straight through from the caller (no invented clock)
    assert d["build_id"] == _BUILD_ID
    assert d["build_version"] == _BUILD_VERSION
    assert d["created_at"] == _CREATED_AT
    assert d["community_id"] == _MAIN


def test_material_vs_property_split(store: KuzuGraphStore) -> None:
    payload = build_payload(
        store, _MAIN, build_id=_BUILD_ID, build_version=_BUILD_VERSION, created_at=_CREATED_AT
    )
    assert payload.entity_ids == ["mat-copper", "mat-steel", "prop-hardness", "tech-quench"]
    assert payload.material_ids == ["mat-copper", "mat-steel"]
    assert payload.property_ids == ["prop-hardness"]
    # the technology solution is a member entity but neither a material nor a property
    assert "tech-quench" in payload.entity_ids
    assert "tech-quench" not in payload.material_ids
    assert "tech-quench" not in payload.property_ids
    # materials & properties are disjoint subsets of entity_ids
    assert set(payload.material_ids).isdisjoint(payload.property_ids)
    assert set(payload.material_ids) | set(payload.property_ids) <= set(payload.entity_ids)


def test_doc_ids_gathered_via_supported_by(store: KuzuGraphStore) -> None:
    payload = build_payload(
        store, _MAIN, build_id=_BUILD_ID, build_version=_BUILD_VERSION, created_at=_CREATED_AT
    )
    # paperA via a direct Evidence target; paperB via the SUPPORTED_BY edge evidence_ids
    assert payload.doc_ids == ["paperA.pdf", "paperB.pdf"]
    assert len(payload.doc_ids) == len(set(payload.doc_ids))  # deduplicated


def test_report_fields_from_finding(store: KuzuGraphStore) -> None:
    payload = build_payload(
        store, _MAIN, build_id=_BUILD_ID, build_version=_BUILD_VERSION, created_at=_CREATED_AT
    )
    assert payload.title == "Cluster #5"
    assert payload.summary == "Steel and copper hardness cluster."
    assert payload.findings == ["Steel and copper hardness cluster."]
    # level/rank read from the Finding's custom props via get_node (not query columns)
    assert payload.level == 1
    assert payload.rank == 4.0


def test_empty_community_is_well_formed(store: KuzuGraphStore) -> None:
    payload = build_payload(
        store, _EMPTY, build_id=_BUILD_ID, build_version=_BUILD_VERSION, created_at=_CREATED_AT
    )
    assert payload.community_id == _EMPTY
    assert payload.entity_ids == []
    assert payload.material_ids == []
    assert payload.property_ids == []
    assert payload.doc_ids == []
    assert payload.findings == []
    assert payload.title == ""
    assert payload.summary == ""
    assert payload.level == 0
    assert payload.rank == 0.0
    # build metadata is still populated even for an empty community
    assert payload.build_id == _BUILD_ID
    assert set(payload.as_dict()) == _EXPECTED_KEYS


def test_from_dict_as_dict_round_trip(store: KuzuGraphStore) -> None:
    payload = build_payload(
        store, _MAIN, build_id=_BUILD_ID, build_version=_BUILD_VERSION, created_at=_CREATED_AT
    )
    restored = CommunityReportPayload.from_dict(payload.as_dict())
    assert restored == payload
    # round-trip preserves each list field by value
    assert restored.material_ids == payload.material_ids
    assert restored.doc_ids == payload.doc_ids
    assert restored.findings == payload.findings
    # as_dict returns copies — mutating the dict must not corrupt the frozen record
    d = payload.as_dict()
    d["material_ids"].append("tampered")
    d["doc_ids"].append("tampered.pdf")
    assert "tampered" not in payload.material_ids
    assert "tampered.pdf" not in payload.doc_ids


def _sample_payloads() -> list[CommunityReportPayload]:
    return [
        CommunityReportPayload(
            community_id=1,
            level=0,
            title="root",
            rank=9.0,
            summary="root cluster",
            material_ids=["mat-steel", "mat-copper"],
        ),
        CommunityReportPayload(
            community_id=2,
            level=1,
            title="steel sub",
            rank=5.0,
            summary="steel subcluster",
            material_ids=["mat-steel"],
        ),
        CommunityReportPayload(
            community_id=3,
            level=1,
            title="water sub",
            rank=4.0,
            summary="water subcluster",
            material_ids=["mat-water"],
        ),
    ]


def test_level_filter() -> None:
    payloads = _sample_payloads()
    level1 = search_payloads(payloads, level=1)
    assert [p.community_id for p in level1] == [2, 3]
    level0 = search_payloads(payloads, level=0)
    assert [p.community_id for p in level0] == [1]
    # level=None disables the filter (all pass, order preserved)
    assert search_payloads(payloads) == payloads


def test_material_ids_filter() -> None:
    payloads = _sample_payloads()
    # set-intersection membership: matches root (has steel) and the steel subcluster
    steel = search_payloads(payloads, material_ids=["mat-steel"])
    assert [p.community_id for p in steel] == [1, 2]
    # combined level + material filter narrows to the steel subcluster only
    steel_l1 = search_payloads(payloads, level=1, material_ids=["mat-steel"])
    assert [p.community_id for p in steel_l1] == [2]
    # a material present in no payload yields an empty result
    assert search_payloads(payloads, material_ids=["mat-gold"]) == []
