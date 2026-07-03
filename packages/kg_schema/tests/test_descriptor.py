"""Tests for the machine-readable schema descriptor (§3.17)."""

from __future__ import annotations

import json

from kg_schema.descriptor import (
    ENUM_REGISTRY,
    RelationshipSignature,
    SchemaDescriptor,
    build_schema_descriptor,
)
from kg_schema.enums import GapType, MetallurgicalDomain, VerificationLevel
from kg_schema.labels import NodeLabel, RunLabel
from kg_schema.relationships import EDGE_SCHEMA


def test_labels_count_matches_kg_schema() -> None:
    # 44 NodeLabel + 2 RunLabel = 46 node labels, comfortably >= 30 (§8.1 / §8.2).
    desc = build_schema_descriptor()
    assert len(list(NodeLabel)) == 44
    assert len(list(RunLabel)) == 2
    assert len(desc.labels) == 46
    assert len(desc.labels) >= 30


def test_every_node_label_present() -> None:
    # Every NodeLabel and RunLabel value is enumerated, in declaration order.
    desc = build_schema_descriptor()
    for label in NodeLabel:
        assert label.value in desc.labels
    assert "ExtractorRun" in desc.labels
    assert "GapScanRun" in desc.labels
    assert desc.labels[0] == "Document"
    assert desc.labels[-1] == "GapScanRun"


def test_no_duplicate_labels() -> None:
    desc = build_schema_descriptor()
    assert len(desc.labels) == len(set(desc.labels))


def test_every_relationship_has_from_rel_to() -> None:
    # One signature per EDGE_SCHEMA entry (71), each with non-empty from/rel/to.
    desc = build_schema_descriptor()
    assert len(desc.relationships) == len(EDGE_SCHEMA) == 71
    for sig in desc.relationships:
        assert isinstance(sig, RelationshipSignature)
        assert sig.from_label and sig.rel and sig.to_label
        d = sig.as_dict()
        assert set(d) == {"from", "rel", "to"}
        assert all(d.values())


def test_relationship_signature_known_edges() -> None:
    # Hand-checkable: specific declared edges survive into the descriptor (§3.5).
    desc = build_schema_descriptor()
    edges = {(s.from_label, s.rel, s.to_label) for s in desc.relationships}
    assert ("Document", "HAS_SECTION", "Section") in edges
    assert ("Measurement", "OF_PROPERTY", "Property") in edges
    # Virtual super-label Entity is preserved verbatim in MENTIONS.
    assert ("Chunk", "MENTIONS", "Entity") in edges


def test_enums_include_key_enums() -> None:
    # Key enums are addressable by stable name with their exact value sets (§3.17).
    desc = build_schema_descriptor()
    assert "domain" in desc.enums
    assert "verification_level" in desc.enums
    assert desc.enums["domain"] == tuple(e.value for e in MetallurgicalDomain)
    assert desc.enums["domain"][0] == "hydrometallurgy"
    assert desc.enums["verification_level"] == tuple(e.value for e in VerificationLevel)
    assert desc.enums["verification_level"][0] == "confirmed"
    assert "obsolete" in desc.enums["verification_level"]


def test_enum_registry_values_match_source() -> None:
    # Every registered enum maps to the ordered tuple of its member values.
    desc = build_schema_descriptor()
    assert set(desc.enums) == set(ENUM_REGISTRY)
    for name, enum_cls in ENUM_REGISTRY.items():
        assert desc.enums[name] == tuple(m.value for m in enum_cls)
    assert desc.enums["gap_type"] == tuple(g.value for g in GapType)
    assert len(desc.enums["gap_type"]) == 16


def test_version_present() -> None:
    desc = build_schema_descriptor()
    assert desc.version == "0.1.0"
    assert desc.as_dict()["version"] == "0.1.0"
    # Caller may pin an explicit version (e.g. a migration snapshot, §23.4).
    pinned = build_schema_descriptor(version="1.4.0")
    assert pinned.version == "1.4.0"


def test_as_dict_shape() -> None:
    desc = build_schema_descriptor()
    d = desc.as_dict()
    assert set(d) == {"labels", "relationships", "enums", "version"}
    assert isinstance(d["labels"], list)
    assert isinstance(d["relationships"], list)
    assert isinstance(d["enums"], dict)
    assert d["labels"][0] == "Document"
    assert d["relationships"][0] == {"from": "Document", "rel": "HAS_SECTION", "to": "Section"}
    # as_dict returns fresh containers: mutating them must not touch the descriptor.
    d["labels"].append("BOGUS")
    d["enums"]["domain"].append("bogus")
    assert "BOGUS" not in desc.labels
    assert "bogus" not in desc.enums["domain"]


def test_to_json_round_trip() -> None:
    desc = build_schema_descriptor()
    loaded = json.loads(desc.to_json())
    assert loaded == desc.as_dict()
    assert loaded["version"] == "0.1.0"
    assert loaded["relationships"][0] == {
        "from": "Document",
        "rel": "HAS_SECTION",
        "to": "Section",
    }
    # indent is a pure formatting knob: same parsed payload either way.
    assert json.loads(desc.to_json(indent=2)) == loaded


def test_descriptor_is_frozen() -> None:
    desc = build_schema_descriptor()
    assert isinstance(desc, SchemaDescriptor)
    for attr, value in (("version", "x"), ("labels", ())):
        try:
            setattr(desc, attr, value)
        except AttributeError:
            continue
        raise AssertionError(f"SchemaDescriptor.{attr} should be immutable")
