"""Tests for §10.3 dataPlatform registry — hand-checkable, concrete values."""

from __future__ import annotations

from kg_common.metadata.data_platforms import (
    PLATFORMS,
    DataPlatform,
    get_platform,
    list_keys,
    platform_urns,
)


def test_exactly_six_platforms() -> None:
    assert len(PLATFORMS) == 6


def test_all_keys_present() -> None:
    keys = {p.key for p in PLATFORMS}
    assert keys == {"kg-source", "neo4j-kg", "qdrant", "opensearch", "minio", "postgres"}


def test_kinds_are_correct() -> None:
    kinds = {p.key: p.kind for p in PLATFORMS}
    assert kinds == {
        "kg-source": "source",
        "neo4j-kg": "graph",
        "qdrant": "vector",
        "opensearch": "keyword",
        "minio": "objectstore",
        "postgres": "rdbms",
    }


def test_get_platform_neo4j_kind() -> None:
    p = get_platform("neo4j-kg")
    assert p is not None
    assert p.kind == "graph"


def test_get_platform_qdrant_kind() -> None:
    p = get_platform("qdrant")
    assert p is not None
    assert p.kind == "vector"


def test_get_platform_missing_is_none() -> None:
    assert get_platform("missing") is None


def test_list_keys_contains_kg_source() -> None:
    assert "kg-source" in list_keys()


def test_list_keys_is_sorted() -> None:
    assert list_keys() == tuple(sorted(list_keys()))


def test_list_keys_exact() -> None:
    assert list_keys() == (
        "kg-source",
        "minio",
        "neo4j-kg",
        "opensearch",
        "postgres",
        "qdrant",
    )


def test_platform_urns_minio() -> None:
    assert platform_urns()["minio"] == "urn:li:dataPlatform:minio"


def test_platform_urns_length() -> None:
    assert len(platform_urns()) == 6


def test_platform_urns_all_values() -> None:
    assert platform_urns() == {
        "kg-source": "urn:li:dataPlatform:kg-source",
        "neo4j-kg": "urn:li:dataPlatform:neo4j-kg",
        "qdrant": "urn:li:dataPlatform:qdrant",
        "opensearch": "urn:li:dataPlatform:opensearch",
        "minio": "urn:li:dataPlatform:minio",
        "postgres": "urn:li:dataPlatform:postgres",
    }


def test_dataplatform_urn_method() -> None:
    assert DataPlatform(key="minio", name="MinIO", kind="objectstore").urn() == (
        "urn:li:dataPlatform:minio"
    )


def test_as_dict_shape() -> None:
    d = get_platform("qdrant").as_dict()  # type: ignore[union-attr]
    assert d == {
        "key": "qdrant",
        "name": "Qdrant",
        "kind": "vector",
        "urn": "urn:li:dataPlatform:qdrant",
    }


def test_dataplatform_is_frozen() -> None:
    import dataclasses

    import pytest

    p = get_platform("minio")
    assert p is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.kind = "changed"  # type: ignore[misc]
