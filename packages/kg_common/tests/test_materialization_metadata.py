"""Tests for asset materialization metadata — тесты метаданных материализации (§9.8)."""

from __future__ import annotations

from kg_common.materialization_metadata import (
    MaterializationMetadata,
    build_metadata,
    merge_counts,
    total_count,
)


def test_build_metadata_preserves_counts() -> None:
    md = build_metadata("graph_upsert", counts={"nodes": 3, "edges": 5})
    assert md.asset_key == "graph_upsert"
    assert md.counts == {"nodes": 3, "edges": 5}


def test_total_count_sums_values() -> None:
    assert total_count(build_metadata("x", counts={"a": 2, "b": 4})) == 6


def test_total_count_empty_is_zero() -> None:
    assert total_count(build_metadata("x", counts={})) == 0


def test_merge_counts_sums_overlap() -> None:
    assert merge_counts({"a": 1, "b": 2}, {"b": 3, "c": 1}) == {"a": 1, "b": 5, "c": 1}


def test_merge_counts_does_not_mutate_inputs() -> None:
    a = {"a": 1, "b": 2}
    b = {"b": 3, "c": 1}
    merge_counts(a, b)
    assert a == {"a": 1, "b": 2}
    assert b == {"b": 3, "c": 1}


def test_as_dict_artifact_uris_is_list() -> None:
    md = build_metadata("x", counts={}, artifact_uris=("s3://a",))
    assert md.as_dict()["artifact_uris"] == ["s3://a"]


def test_as_dict_omits_none_extraction_run_id() -> None:
    assert "extraction_run_id" not in build_metadata("x", counts={}).as_dict()


def test_as_dict_omits_none_schema_version() -> None:
    assert "schema_version" not in build_metadata("x", counts={}).as_dict()


def test_as_dict_omits_none_partition_key() -> None:
    assert "partition_key" not in build_metadata("x", counts={}).as_dict()


def test_as_dict_emits_extraction_run_id_when_set() -> None:
    md = build_metadata("x", counts={}, extraction_run_id="run:1")
    assert md.as_dict()["extraction_run_id"] == "run:1"


def test_as_dict_emits_partition_key_when_set() -> None:
    md = build_metadata("x", counts={}, partition_key="doc-1")
    assert md.as_dict()["partition_key"] == "doc-1"


def test_as_dict_emits_schema_version_when_set() -> None:
    md = build_metadata("x", counts={}, schema_version="v3")
    assert md.as_dict()["schema_version"] == "v3"


def test_as_dict_always_present_fields() -> None:
    d = build_metadata("asset-1", counts={"rows": 7}).as_dict()
    assert d["asset_key"] == "asset-1"
    assert d["counts"] == {"rows": 7}
    assert d["artifact_uris"] == []


def test_default_counts_is_empty() -> None:
    assert build_metadata("x").counts == {}


def test_frozen_record_is_immutable() -> None:
    md = build_metadata("x", counts={"a": 1})
    try:
        md.asset_key = "y"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must forbid assignment
        raise AssertionError("MaterializationMetadata must be frozen")


def test_build_metadata_copies_counts_defensively() -> None:
    src = {"a": 1}
    md = build_metadata("x", counts=src)
    src["a"] = 99
    assert md.counts == {"a": 1}


def test_as_dict_counts_is_a_copy() -> None:
    md = build_metadata("x", counts={"a": 1})
    d = md.as_dict()
    assert isinstance(d["counts"], dict)
    d["counts"]["a"] = 42  # type: ignore[index]
    assert md.counts == {"a": 1}


def test_type_exported() -> None:
    assert isinstance(build_metadata("x"), MaterializationMetadata)
