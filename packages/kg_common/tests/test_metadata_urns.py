"""URN builder/parser tests (§10.3)."""

from __future__ import annotations

import pytest

from kg_common.metadata.urns import (
    Urn,
    build_dataset_urn,
    build_platform_urn,
    is_valid_urn,
    parse_urn,
)


def test_build_platform_urn() -> None:
    assert build_platform_urn("kg-source") == "urn:li:dataPlatform:kg-source"


def test_build_dataset_urn_default_env() -> None:
    assert (
        build_dataset_urn("kg-source", "s1")
        == "urn:li:dataset:(urn:li:dataPlatform:kg-source,s1,PROD)"
    )


def test_build_dataset_urn_custom_env() -> None:
    urn = build_dataset_urn("qdrant", "c1", env="DEV")
    assert urn == "urn:li:dataset:(urn:li:dataPlatform:qdrant,c1,DEV)"
    assert ",DEV)" in urn


def test_parse_roundtrip() -> None:
    parsed = parse_urn(build_dataset_urn("neo4j-kg", "kg"))
    assert parsed.entity_type == "dataset"
    assert parsed.platform == "neo4j-kg"
    assert parsed.name == "kg"
    assert parsed.env == "PROD"


def test_parse_custom_env_roundtrip() -> None:
    parsed = parse_urn(build_dataset_urn("qdrant", "c1", env="DEV"))
    assert parsed == Urn(entity_type="dataset", platform="qdrant", name="c1", env="DEV")


def test_urn_as_dict() -> None:
    parsed = parse_urn(build_dataset_urn("neo4j-kg", "kg"))
    assert parsed.as_dict() == {
        "entity_type": "dataset",
        "platform": "neo4j-kg",
        "name": "kg",
        "env": "PROD",
    }


def test_is_valid_urn_true() -> None:
    assert is_valid_urn("urn:li:dataset:(urn:li:dataPlatform:x,y,PROD)") is True


def test_is_valid_urn_false() -> None:
    assert is_valid_urn("nonsense") is False
    assert is_valid_urn(build_platform_urn("kg-source")) is False


def test_parse_urn_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_urn("bad")
