"""Tests for §5.8 per-format parser priority resolver."""

from __future__ import annotations

import json

from ingestion_service.parser_priority import (
    DEFAULT_TABLE,
    PriorityTable,
    merge_overrides,
    resolve_order,
)


def test_default_pdf_prefers_docling() -> None:
    assert resolve_order(DEFAULT_TABLE, "pdf")[0] == "docling"


def test_default_html_prefers_unstructured() -> None:
    assert resolve_order(DEFAULT_TABLE, "html")[0] == "unstructured"


def test_fmt_normalization_dot_and_case() -> None:
    # '.PDF' → 'pdf' after strip-dot + lowercase.
    assert resolve_order(DEFAULT_TABLE, ".PDF") == resolve_order(DEFAULT_TABLE, "pdf")
    assert resolve_order(DEFAULT_TABLE, "  .HtMl ") == resolve_order(DEFAULT_TABLE, "html")


def test_unknown_fmt_returns_default() -> None:
    assert resolve_order(DEFAULT_TABLE, "xyz") == DEFAULT_TABLE.default
    assert resolve_order(DEFAULT_TABLE, ".unknown") == ("default",)


def test_merge_overrides_replaces_only_given_format() -> None:
    overrides = {"pdf": ("unstructured", "docling")}
    merged = merge_overrides(DEFAULT_TABLE, overrides)
    # The overridden format changed...
    assert resolve_order(merged, "pdf") == ("unstructured", "docling")
    # ...but other formats are untouched.
    assert resolve_order(merged, "html") == resolve_order(DEFAULT_TABLE, "html")
    assert resolve_order(merged, "docx") == resolve_order(DEFAULT_TABLE, "docx")


def test_merge_overrides_normalizes_override_keys() -> None:
    merged = merge_overrides(DEFAULT_TABLE, {".DOCX": ("unstructured",)})
    assert resolve_order(merged, "docx") == ("unstructured",)


def test_merge_overrides_returns_new_table_base_unchanged() -> None:
    merged = merge_overrides(DEFAULT_TABLE, {"pdf": ("unstructured",)})
    assert merged is not DEFAULT_TABLE
    assert isinstance(merged, PriorityTable)
    # Base is unchanged: original pdf order is preserved.
    assert resolve_order(DEFAULT_TABLE, "pdf") == ("docling", "unstructured", "default")


def test_as_dict_is_json_safe_dict_of_lists() -> None:
    d = DEFAULT_TABLE.as_dict()
    assert isinstance(d["order"], dict)
    for fmt, parsers in d["order"].items():
        assert isinstance(fmt, str)
        assert isinstance(parsers, list)
        assert all(isinstance(p, str) for p in parsers)
    assert isinstance(d["default"], list)
    # Round-trips through JSON without error.
    assert json.loads(json.dumps(d)) == d


def test_default_office_formats_prefer_docling() -> None:
    assert resolve_order(DEFAULT_TABLE, "docx")[0] == "docling"
    assert resolve_order(DEFAULT_TABLE, "pptx")[0] == "docling"


def test_empty_table_falls_back_to_default() -> None:
    table = PriorityTable(default=("default",))
    assert resolve_order(table, "pdf") == ("default",)
    assert table.as_dict() == {"order": {}, "default": ["default"]}
