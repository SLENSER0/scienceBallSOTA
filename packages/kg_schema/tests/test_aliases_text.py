"""Tests for fulltext ``aliases_text`` assembly (§3.8/§3.12)."""

from __future__ import annotations

from kg_schema.aliases_text import (
    SURFACE_SEPARATOR,
    AliasText,
    build_aliases_text,
    surfaces_of,
)


def test_dedupe_casefold_keeps_first_surface() -> None:
    result = build_aliases_text("Al-Cu 2024", "Al-Cu 2024", ["AA2024", "al-cu 2024"])
    assert result.surfaces == ("Al-Cu 2024", "AA2024")


def test_text_joined_with_separator() -> None:
    result = build_aliases_text("Al-Cu 2024", "Al-Cu 2024", ["AA2024", "al-cu 2024"])
    assert result.text == "Al-Cu 2024 | AA2024"
    assert SURFACE_SEPARATOR == " | "


def test_all_none_is_empty() -> None:
    result = build_aliases_text(None, None, None)
    assert result.surfaces == ()
    assert result.text == ""
    assert result.canonical == ""


def test_alias_duplicate_of_name_dropped() -> None:
    result = build_aliases_text("AA2024", None, ["aa2024"])
    assert result.surfaces == ("AA2024",)
    assert result.text == "AA2024"


def test_order_preserved_first_appearance_name_then_aliases() -> None:
    result = build_aliases_text("A", None, ["B", "C", "a", "D"])
    assert result.surfaces == ("A", "B", "C", "D")


def test_blank_alias_dropped() -> None:
    result = build_aliases_text("X", None, ["  "])
    assert result.surfaces == ("X",)


def test_surfaces_of_reads_node_mapping() -> None:
    assert surfaces_of({"name": "X", "aliases": ["Y"]}) == ("X", "Y")


def test_surfaces_of_missing_keys() -> None:
    assert surfaces_of({}) == ()
    assert surfaces_of({"canonical_name": "Z"}) == ("Z",)


def test_as_dict_text_field() -> None:
    assert AliasText("c", ("X",), "X").as_dict()["text"] == "X"


def test_as_dict_full_shape() -> None:
    at = AliasText("Al-Cu 2024", ("Al-Cu 2024", "AA2024"), "Al-Cu 2024 | AA2024")
    assert at.as_dict() == {
        "canonical": "Al-Cu 2024",
        "surfaces": ["Al-Cu 2024", "AA2024"],
        "text": "Al-Cu 2024 | AA2024",
    }


def test_canonical_falls_back_to_canonical_name() -> None:
    result = build_aliases_text(None, "Copper", ["Cu"])
    assert result.canonical == "Copper"
    assert result.surfaces == ("Copper", "Cu")


def test_whitespace_stripped_from_surfaces() -> None:
    result = build_aliases_text("  Steel  ", None, ["  S235  "])
    assert result.surfaces == ("Steel", "S235")
