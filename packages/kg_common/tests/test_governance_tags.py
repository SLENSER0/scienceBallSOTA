"""Tests for the governance tag catalog — тесты каталога тегов (§10.3/§10.11)."""

from __future__ import annotations

import pytest

from kg_common.governance_tags import (
    ACCESS_VALUES,
    DOMAIN_VALUES,
    PII_VALUES,
    QUALITY_VALUES,
    GovernanceTag,
    access_tag,
    is_valid_tag,
    normalize_tags,
    parse_tag,
    quality_tag,
)


def test_catalog_constants() -> None:
    assert ACCESS_VALUES == ("public", "internal", "restricted")
    assert QUALITY_VALUES == ("verified", "pending")
    assert PII_VALUES == ("none",)
    assert DOMAIN_VALUES == ("materials",)


def test_tag_to_str_and_as_dict() -> None:
    assert access_tag("public").to_str() == "access:public"
    assert GovernanceTag("access", "internal").as_dict() == {
        "facet": "access",
        "value": "internal",
    }
    assert quality_tag("verified").to_str() == "quality:verified"


def test_tag_is_frozen() -> None:
    tag = GovernanceTag("access", "public")
    with pytest.raises((AttributeError, TypeError)):
        tag.value = "internal"  # type: ignore[misc]


def test_parse_tag_roundtrip() -> None:
    assert parse_tag("quality:pending") == GovernanceTag("quality", "pending")
    assert parse_tag("access:restricted") == access_tag("restricted")
    assert parse_tag("domain:materials") == GovernanceTag("domain", "materials")
    # Round-trip: to_str then parse yields the same tag.
    tag = GovernanceTag("pii", "none")
    assert parse_tag(tag.to_str()) == tag


def test_parse_tag_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse_tag("quality")  # no ':'
    with pytest.raises(ValueError):
        parse_tag("access:secret")  # unknown value
    with pytest.raises(ValueError):
        parse_tag("unknown:x")  # unknown facet


def test_is_valid_tag() -> None:
    assert is_valid_tag("access:secret") is False
    assert is_valid_tag("pii:none") is True
    assert is_valid_tag("quality") is False
    assert is_valid_tag("access:public") is True
    assert is_valid_tag("domain:materials") is True
    assert is_valid_tag("domain:chemistry") is False


def test_access_tag_raises_on_unknown() -> None:
    with pytest.raises(ValueError):
        access_tag("foo")


def test_quality_tag_raises_on_unknown() -> None:
    with pytest.raises(ValueError):
        quality_tag("draft")


def test_normalize_tags_dedup_and_sort() -> None:
    assert normalize_tags(["domain:materials", "access:public", "access:public"]) == (
        GovernanceTag("access", "public"),
        GovernanceTag("domain", "materials"),
    )


def test_normalize_tags_sorts_by_facet_then_value() -> None:
    result = normalize_tags(
        [
            "quality:pending",
            "access:restricted",
            "access:internal",
            "pii:none",
        ]
    )
    assert result == (
        GovernanceTag("access", "internal"),
        GovernanceTag("access", "restricted"),
        GovernanceTag("pii", "none"),
        GovernanceTag("quality", "pending"),
    )


def test_normalize_tags_empty() -> None:
    assert normalize_tags([]) == ()


def test_normalize_tags_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_tags(["access:public", "access:secret"])
