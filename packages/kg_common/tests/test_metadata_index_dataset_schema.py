"""Tests for §10.4 index/store dataset schema descriptor.

RU: Проверки дескриптора схемы Qdrant/OpenSearch (§10.4).
EN: Hand-checkable tests for the Qdrant/OpenSearch schema descriptor (§10.4).
"""

from __future__ import annotations

import pytest

from kg_common.metadata.index_dataset_schema import (
    VectorIndexSchema,
    opensearch_index_schema,
    qdrant_collection_schema,
    to_schema_fields,
)


def test_qdrant_lowercases_distance() -> None:
    s = qdrant_collection_schema("c", 768, "COSINE", ("doc_id", "lab"))
    assert s.distance == "cosine"
    assert s.platform == "qdrant"
    assert s.dim == 768
    assert s.payload_fields == ("doc_id", "lab")


def test_qdrant_accepts_all_valid_metrics() -> None:
    for raw, want in (("cosine", "cosine"), ("DOT", "dot"), ("L2", "l2")):
        assert qdrant_collection_schema("c", 4, raw, ()).distance == want


def test_qdrant_rejects_unknown_distance() -> None:
    with pytest.raises(ValueError):
        qdrant_collection_schema("c", 768, "hamming", ())


def test_qdrant_rejects_zero_dim() -> None:
    with pytest.raises(ValueError):
        qdrant_collection_schema("c", 0, "cosine", ())


def test_qdrant_rejects_negative_dim() -> None:
    with pytest.raises(ValueError):
        qdrant_collection_schema("c", -1, "cosine", ())


def test_to_schema_fields_vector_first() -> None:
    fields = to_schema_fields(qdrant_collection_schema("c", 768, "cosine", ("doc_id",)))
    assert fields[0]["nativeType"] == "vector[768]"
    assert fields[0]["name"] == "c"
    assert len(fields) == 2
    assert fields[1] == {"name": "doc_id", "nativeType": "keyword"}


def test_opensearch_has_no_vector() -> None:
    s = opensearch_index_schema("k", ("title", "body"))
    assert s.dim == 0
    assert s.distance == "none"
    assert s.platform == "opensearch"
    fields = to_schema_fields(s)
    assert len(fields) == 2
    assert all(f["nativeType"] == "keyword" for f in fields)
    assert [f["name"] for f in fields] == ["title", "body"]


def test_qdrant_dedup_preserves_order() -> None:
    s = qdrant_collection_schema("c", 8, "cosine", ("a", "a", "b"))
    assert s.payload_fields == ("a", "b")


def test_opensearch_dedup_preserves_order() -> None:
    s = opensearch_index_schema("k", ("b", "a", "b", "c", "a"))
    assert s.payload_fields == ("b", "a", "c")


def test_as_dict_payload_fields_is_list() -> None:
    d = VectorIndexSchema("c", "qdrant", 768, "cosine", ("doc_id", "lab")).as_dict()
    assert isinstance(d["payload_fields"], list)
    assert d["payload_fields"] == ["doc_id", "lab"]
    assert d == {
        "name": "c",
        "platform": "qdrant",
        "dim": 768,
        "distance": "cosine",
        "payload_fields": ["doc_id", "lab"],
    }


def test_frozen_schema_is_immutable() -> None:
    s = qdrant_collection_schema("c", 4, "cosine", ("a",))
    with pytest.raises(AttributeError):
        s.dim = 8  # type: ignore[misc]


def test_no_payload_vector_only() -> None:
    fields = to_schema_fields(qdrant_collection_schema("c", 16, "dot", ()))
    assert fields == [{"name": "c", "nativeType": "vector[16]"}]
