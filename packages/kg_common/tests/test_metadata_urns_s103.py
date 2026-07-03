"""Tests for §10.3 DataHub-style URN builder/parser (metadata_urns)."""

from __future__ import annotations

import pytest

from kg_common.metadata_urns import (
    Urn,
    dataset_urn,
    document_urn,
    is_valid_urn,
    parse_urn,
    source_urn,
)


def test_dataset_urn_default_env() -> None:
    assert dataset_urn("neo4j-kg", "core") == (
        "urn:li:dataset:(urn:li:dataPlatform:neo4j-kg,core,PROD)"
    )


def test_dataset_urn_custom_env() -> None:
    assert dataset_urn("qdrant", "chunks", env="DEV") == (
        "urn:li:dataset:(urn:li:dataPlatform:qdrant,chunks,DEV)"
    )


def test_source_urn_shape() -> None:
    assert source_urn("s1") == "urn:li:dataset:(urn:li:dataPlatform:kg-source,s1,PROD)"


def test_document_urn_shape() -> None:
    assert document_urn("d1") == ("urn:li:dataset:(urn:li:dataPlatform:kg-document,d1,PROD)")


def test_parse_source_urn() -> None:
    parsed = parse_urn(source_urn("s1"))
    assert parsed.platform == "kg-source"
    assert parsed.key == "s1"
    assert parsed.entity_type == "dataset"
    assert parsed.env == "PROD"


def test_parse_roundtrip_dataset() -> None:
    u = Urn("qdrant", "dataset", "chunks")
    assert parse_urn(str(u)).to_str() == str(u)


def test_parse_roundtrip_custom_env() -> None:
    u = Urn("qdrant", "dataset", "chunks", env="STG")
    assert parse_urn(str(u)) == u


def test_is_valid_urn_false() -> None:
    assert is_valid_urn("not-a-urn") is False


def test_is_valid_urn_document_true() -> None:
    assert is_valid_urn(document_urn("d1")) is True


def test_as_dict_env() -> None:
    assert Urn("kg-source", "dataset", "s1").as_dict()["env"] == "PROD"


def test_as_dict_full() -> None:
    assert Urn("kg-source", "dataset", "s1").as_dict() == {
        "platform": "kg-source",
        "entity_type": "dataset",
        "key": "s1",
        "env": "PROD",
    }


def test_parse_non_dataset_entity() -> None:
    parsed = parse_urn("urn:li:corpuser:alice")
    assert parsed.entity_type == "corpuser"
    assert parsed.key == "alice"
    assert parsed.platform == ""


def test_non_dataset_roundtrip() -> None:
    u = parse_urn("urn:li:corpuser:alice")
    assert u.to_str() == "urn:li:corpuser:alice"
    assert parse_urn(u.to_str()) == u


def test_is_valid_urn_non_dataset_true() -> None:
    assert is_valid_urn("urn:li:corpuser:alice") is True


def test_parse_urn_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_urn("bad")


def test_parse_urn_bad_dataset_body_raises() -> None:
    with pytest.raises(ValueError):
        parse_urn("urn:li:dataset:(urn:li:dataPlatform:only,two)")


def test_str_matches_to_str() -> None:
    u = Urn("neo4j-kg", "dataset", "core")
    assert str(u) == u.to_str()
