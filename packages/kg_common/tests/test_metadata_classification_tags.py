"""Tests for governance classification tags — тесты тегов классификации (§10.3)."""

from __future__ import annotations

from kg_common.metadata.classification_tags import (
    ACCESS_LEVELS,
    PII_LEVELS,
    QUALITY_LEVELS,
    Classification,
    is_valid_tag,
    parse_tag,
)


def test_allowed_value_sets() -> None:
    assert set(ACCESS_LEVELS) == {"public", "internal", "restricted"}
    assert set(PII_LEVELS) == {"none", "present"}
    assert set(QUALITY_LEVELS) == {"verified", "pending"}
    assert isinstance(ACCESS_LEVELS, frozenset)


def test_defaults() -> None:
    c = Classification("public")
    assert c.access == "public"
    assert c.pii == "none"
    assert c.quality == "pending"
    assert c.domain == "materials"


def test_to_tags_default_sorted() -> None:
    assert Classification("public").to_tags() == (
        "access:public",
        "domain:materials",
        "pii:none",
        "quality:pending",
    )


def test_to_tags_verified_quality() -> None:
    tags = Classification("restricted", quality="verified").to_tags()
    assert "quality:verified" in tags
    assert "access:restricted" in tags
    # Sorted order preserved.
    assert list(tags) == sorted(tags)


def test_as_dict() -> None:
    assert Classification("internal").as_dict()["access"] == "internal"
    assert Classification("internal", pii="present").as_dict() == {
        "access": "internal",
        "pii": "present",
        "quality": "pending",
        "domain": "materials",
    }


def test_parse_tag() -> None:
    assert parse_tag("access:internal") == ("access", "internal")
    # Split on the *first* colon only.
    assert parse_tag("domain:a:b") == ("domain", "a:b")
    # No colon → value empty.
    assert parse_tag("bare") == ("bare", "")


def test_is_valid_tag_closed_namespaces() -> None:
    assert is_valid_tag("access:public") is True
    assert is_valid_tag("access:secret") is False
    assert is_valid_tag("pii:none") is True
    assert is_valid_tag("pii:maybe") is False
    assert is_valid_tag("quality:verified") is True
    assert is_valid_tag("quality:bogus") is False


def test_is_valid_tag_domain_freeform() -> None:
    assert is_valid_tag("domain:materials") is True
    assert is_valid_tag("domain:biology") is True
    # Empty value rejected even for free-form namespace.
    assert is_valid_tag("domain:") is False


def test_is_valid_tag_unknown_namespace() -> None:
    assert is_valid_tag("color:red") is False
    # Missing colon entirely.
    assert is_valid_tag("access") is False


def test_frozen_immutable() -> None:
    c = Classification("public")
    import dataclasses

    try:
        c.access = "internal"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Classification should be frozen")
