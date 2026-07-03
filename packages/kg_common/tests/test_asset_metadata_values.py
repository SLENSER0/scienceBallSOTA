"""Tests for asset metadata values — тесты метаданных ассетов (§9.8)."""

from __future__ import annotations

import pytest

from kg_common.asset_metadata_values import (
    MetadataValue,
    build_asset_metadata,
    md_float,
    md_int,
    md_json,
    md_path,
    md_text,
    md_url,
)


def test_md_int_as_dict() -> None:
    """md_int emits the Dagster-shaped dict — форма словаря (§9.8)."""
    assert md_int(5).as_dict() == {"type": "int", "value": 5}


def test_md_int_rejects_float() -> None:
    """md_int rejects a float to avoid truncation — без усечения (§9.8)."""
    with pytest.raises(TypeError):
        md_int(1.5)


def test_md_int_rejects_bool() -> None:
    """md_int rejects bool (a subclass of int) — bool отвергается (§9.8)."""
    with pytest.raises(TypeError):
        md_int(True)


def test_md_url_kind() -> None:
    """md_url tags the value with kind 'url' — вид url (§9.8)."""
    assert md_url("s3://b/k").kind == "url"


def test_md_json_preserves_value() -> None:
    """md_json keeps the structured payload intact — сохранение (§9.8)."""
    assert md_json({"a": 1}).as_dict()["value"] == {"a": 1}


def test_md_float_coerces_int() -> None:
    """md_float coerces int to float — приведение int->float (§9.8)."""
    mv = md_float(3)
    assert mv.kind == "float"
    assert mv.value == 3.0
    assert isinstance(mv.value, float)


def test_md_text_rejects_non_str() -> None:
    """md_text rejects a non-string — только строки (§9.8)."""
    with pytest.raises(TypeError):
        md_text(42)


def test_md_path_kind() -> None:
    """md_path tags the value with kind 'path' — вид path (§9.8)."""
    assert md_path("/tmp/x").kind == "path"


def test_metadata_value_rejects_unknown_kind() -> None:
    """Constructing an unknown kind raises ValueError — неизвестный вид (§9.8)."""
    with pytest.raises(ValueError):
        MetadataValue("bogus", 1)


def test_build_counts_are_int_entries() -> None:
    """Each count becomes an int metadata entry — счётчики int (§9.8)."""
    md = build_asset_metadata(counts={"chunks": 3, "entities": 2})
    assert md["chunks"] == {"type": "int", "value": 3}
    assert md["entities"] == {"type": "int", "value": 2}


def test_build_s3_uris_path_entry() -> None:
    """s3_uris yields a single path-typed entry — путь для s3 (§9.8)."""
    md = build_asset_metadata(counts={"chunks": 1}, s3_uris=["s3://kg-parsed/x"])
    assert md["s3_uris"]["type"] == "path"
    assert "s3://kg-parsed/x" in md["s3_uris"]["value"]


def test_build_extraction_run_id_text_entry() -> None:
    """extraction_run_id adds a text entry — текст для run id (§9.8)."""
    md = build_asset_metadata(counts={"chunks": 1}, extraction_run_id="er:1")
    assert md["extraction_run_id"] == {"type": "text", "value": "er:1"}


def test_build_omitted_optionals_absent() -> None:
    """Omitted optionals produce no keys — нет ключей для пропущенных (§9.8)."""
    md = build_asset_metadata(counts={"chunks": 1})
    assert "s3_uris" not in md
    assert "extraction_run_id" not in md
    assert "schema_version" not in md


def test_build_is_ordered() -> None:
    """Counts precede optionals in insertion order — порядок ключей (§9.8)."""
    md = build_asset_metadata(
        counts={"chunks": 1, "entities": 2},
        s3_uris=["s3://b/k"],
        extraction_run_id="er:1",
        schema_version="v3",
    )
    assert list(md) == ["chunks", "entities", "s3_uris", "extraction_run_id", "schema_version"]
