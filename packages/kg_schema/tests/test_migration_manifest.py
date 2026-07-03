"""Tests for the graph migration manifest (§3.15 — ordered Cypher migrations)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_schema.migration_manifest import (
    Migration,
    MigrationManifest,
    build_manifest,
    checksum,
    parse_migration_filename,
    pending,
)


def test_parse_migration_filename_ok() -> None:
    assert parse_migration_filename("0001_constraints.cypher") == (1, "constraints")


def test_parse_migration_filename_strips_zero_padding() -> None:
    assert parse_migration_filename("0042_add_indexes.cypher") == (42, "add_indexes")


@pytest.mark.parametrize(
    "bad",
    ["bad.cypher", "0001_constraints.sql", "constraints.cypher", "0001.cypher", ""],
)
def test_parse_migration_filename_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_migration_filename(bad)


def test_checksum_deterministic_and_distinct() -> None:
    assert checksum("X") == checksum("X")
    assert checksum("X") != checksum("Y")


def test_build_manifest_sorted_by_number() -> None:
    manifest = build_manifest({"0002_indexes.cypher": "a", "0001_constraints.cypher": "b"})
    assert isinstance(manifest, MigrationManifest)
    assert manifest.migrations[0].number == 1
    assert manifest.migrations[1].number == 2
    assert manifest.migrations[0].name == "constraints"
    assert manifest.migrations[1].name == "indexes"


def test_build_manifest_computes_checksums() -> None:
    manifest = build_manifest({"0001_constraints.cypher": "b"})
    assert manifest.migrations[0].checksum == checksum("b")


def test_build_manifest_duplicate_number_raises() -> None:
    with pytest.raises(ValueError):
        build_manifest({"0001_a.cypher": "x", "0001_b.cypher": "y"})


def test_pending_none_applied_is_all_ascending() -> None:
    manifest = build_manifest(
        {
            "0003_c.cypher": "cc",
            "0001_a.cypher": "aa",
            "0002_b.cypher": "bb",
        }
    )
    result = pending(manifest, set())
    assert result == list(manifest.migrations)
    assert [m.number for m in result] == [1, 2, 3]


def test_pending_all_applied_is_empty() -> None:
    manifest = build_manifest({"0001_a.cypher": "aa", "0002_b.cypher": "bb"})
    all_checksums = {m.checksum for m in manifest.migrations}
    assert pending(manifest, all_checksums) == []


def test_pending_partial_applied() -> None:
    manifest = build_manifest({"0001_a.cypher": "aa", "0002_b.cypher": "bb", "0003_c.cypher": "cc"})
    applied = {manifest.migrations[0].checksum}
    result = pending(manifest, applied)
    assert [m.number for m in result] == [2, 3]


def test_migration_as_dict() -> None:
    migration = Migration(1, "c", "0001_c.cypher", "ab")
    d = migration.as_dict()
    assert d["number"] == 1
    assert d == {
        "number": 1,
        "name": "c",
        "filename": "0001_c.cypher",
        "checksum": "ab",
    }


def test_manifest_as_dict() -> None:
    manifest = build_manifest({"0001_a.cypher": "aa"})
    d = manifest.as_dict()
    assert d["migrations"][0]["number"] == 1
    assert d["migrations"][0]["checksum"] == checksum("aa")


def test_migration_is_frozen() -> None:
    migration = Migration(1, "c", "0001_c.cypher", "ab")
    with pytest.raises(dataclasses.FrozenInstanceError):
        migration.number = 2  # type: ignore[misc]
