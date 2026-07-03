"""Tests for access-policy normalization (§10.6/§10.3) — тесты нормализации."""

from __future__ import annotations

from kg_common.metadata import classification_tags
from kg_common.metadata.access_policy_normalize import (
    DEFAULT_LEVEL,
    SYNONYMS,
    AccessNormalization,
    normalize_access,
    to_tag,
)


def test_public_synonym_matches() -> None:
    result = normalize_access("public")
    assert result.level == "public"
    assert result.tag == "access:public"
    assert result.matched is True


def test_confidential_is_restricted_case_insensitive() -> None:
    result = normalize_access("Confidential")
    assert result.level == "restricted"
    assert result.tag == "access:restricted"
    assert result.matched is True


def test_empty_string_defaults_to_internal_unmatched() -> None:
    result = normalize_access("")
    assert result.level == "internal"
    assert result.level == DEFAULT_LEVEL
    assert result.tag == "access:internal"
    assert result.matched is False
    assert result.raw == ""


def test_none_defaults_to_internal_unmatched() -> None:
    result = normalize_access(None)
    assert result.level == "internal"
    assert result.tag == "access:internal"
    assert result.matched is False
    assert result.raw == ""


def test_open_is_trimmed_and_lowercased() -> None:
    result = normalize_access("  OPEN ")
    assert result.level == "public"
    assert result.tag == "access:public"
    assert result.matched is True
    # raw preserves the stripped (but not lowercased) form.
    assert result.raw == "OPEN"


def test_unknown_non_empty_falls_back_default() -> None:
    result = normalize_access("weird")
    assert result.level == "internal"
    assert result.matched is False
    assert result.raw == "weird"


def test_to_tag_secret_is_restricted() -> None:
    assert to_tag("secret") == "access:restricted"


def test_to_tag_matches_normalize_access() -> None:
    for raw in ["open", "org", "secret", "weird", "", None]:
        assert to_tag(raw) == normalize_access(raw).tag


def test_internal_synonyms_all_map_internal() -> None:
    for raw in ["internal", "org", "company", "team"]:
        assert normalize_access(raw).level == "internal"
        assert normalize_access(raw).matched is True


def test_restricted_synonyms_all_map_restricted() -> None:
    for raw in ["restricted", "confidential", "secret", "private"]:
        assert normalize_access(raw).level == "restricted"


def test_public_synonyms_all_map_public() -> None:
    for raw in ["open", "pub", "public"]:
        assert normalize_access(raw).level == "public"


def test_every_tag_starts_with_access_and_level_valid() -> None:
    samples = [*SYNONYMS, "", "weird", "  Mixed Case ", "unknown-policy"]
    for raw in samples:
        result = normalize_access(raw)
        assert result.tag.startswith("access:")
        assert result.level in classification_tags.ACCESS_LEVELS
        assert result.tag == f"access:{result.level}"


def test_every_synonym_maps_to_valid_level() -> None:
    for level in SYNONYMS.values():
        assert level in classification_tags.ACCESS_LEVELS


def test_produced_tag_is_valid_per_classification_tags() -> None:
    for raw in ["open", "org", "secret", None, "weird"]:
        assert classification_tags.is_valid_tag(normalize_access(raw).tag)


def test_as_dict_shape() -> None:
    result = normalize_access("Confidential")
    assert result.as_dict() == {
        "raw": "Confidential",
        "level": "restricted",
        "tag": "access:restricted",
        "matched": True,
    }


def test_frozen_dataclass_is_immutable() -> None:
    result = normalize_access("open")
    try:
        result.level = "internal"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - should not reach
        raise AssertionError("AccessNormalization must be frozen")


def test_type_is_access_normalization() -> None:
    assert isinstance(normalize_access("open"), AccessNormalization)
