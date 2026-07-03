"""Tests for the evidence-pack manifest — тесты манифеста пакета (§23.29)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError

from kg_common.evidence_pack_manifest import (
    EMPTY_SHA256,
    FileEntry,
    PackManifest,
    build_manifest,
    sha256_hex,
    verify,
)


def test_sha256_hex_empty_matches_known_constant() -> None:
    assert sha256_hex(b"") == EMPTY_SHA256
    assert EMPTY_SHA256 == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_sha256_hex_matches_hashlib() -> None:
    data = b"reproducible evidence pack"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()


def test_file_entry_as_dict() -> None:
    entry = FileEntry(name="a.txt", sha256="deadbeef", size=3)
    assert entry.as_dict() == {"name": "a.txt", "sha256": "deadbeef", "size": 3}


def _sample_files() -> dict[str, bytes]:
    return {"b.txt": b"bbbb", "a.txt": b"aa", "c.bin": b"ccc"}


def test_entries_sorted_lexicographically() -> None:
    manifest = build_manifest(_sample_files())
    names = [entry.name for entry in manifest.entries]
    assert names == ["a.txt", "b.txt", "c.bin"]


def test_total_bytes_is_sum_of_sizes() -> None:
    manifest = build_manifest(_sample_files())
    assert manifest.total_bytes == 2 + 4 + 3
    assert manifest.total_bytes == sum(e.size for e in manifest.entries)


def test_build_manifest_order_independent() -> None:
    files_a = {"a.txt": b"aa", "b.txt": b"bbbb", "c.bin": b"ccc"}
    files_b = {"c.bin": b"ccc", "b.txt": b"bbbb", "a.txt": b"aa"}
    man_a = build_manifest(files_a)
    man_b = build_manifest(files_b)
    assert man_a.root_sha256 == man_b.root_sha256
    assert man_a == man_b


def test_root_sha256_hand_checkable() -> None:
    files = {"a.txt": b"aa", "b.txt": b"bbbb"}
    manifest = build_manifest(files)
    sha_a = hashlib.sha256(b"aa").hexdigest()
    sha_b = hashlib.sha256(b"bbbb").hexdigest()
    expected_lines = f"a.txt:{sha_a}\nb.txt:{sha_b}\n"
    expected_root = hashlib.sha256(expected_lines.encode("utf-8")).hexdigest()
    assert manifest.root_sha256 == expected_root


def test_schema_version_default_and_override() -> None:
    assert build_manifest({}).schema_version == "1"
    assert build_manifest({}, schema_version="2").schema_version == "2"


def test_empty_pack() -> None:
    manifest = build_manifest({})
    assert manifest.entries == ()
    assert manifest.total_bytes == 0
    # root over the empty concatenation is the empty-string digest.
    assert manifest.root_sha256 == EMPTY_SHA256


def test_verify_unchanged_files() -> None:
    files = _sample_files()
    manifest = build_manifest(files)
    assert verify(manifest, files) == (True, ())


def test_verify_mutated_file_flagged() -> None:
    files = _sample_files()
    manifest = build_manifest(files)
    tampered = dict(files)
    tampered["b.txt"] = b"XXXX"
    assert verify(manifest, tampered) == (False, ("b.txt",))


def test_verify_extra_file_ignored() -> None:
    files = _sample_files()
    manifest = build_manifest(files)
    extended = dict(files)
    extended["z-extra.txt"] = b"not in manifest"
    assert verify(manifest, extended) == (True, ())


def test_verify_missing_file_flagged() -> None:
    files = _sample_files()
    manifest = build_manifest(files)
    dropped = dict(files)
    del dropped["a.txt"]
    assert verify(manifest, dropped) == (False, ("a.txt",))


def test_verify_multiple_mismatches_sorted() -> None:
    files = _sample_files()
    manifest = build_manifest(files)
    broken = {"a.txt": b"XX", "b.txt": b"YYYY", "c.bin": b"ccc"}
    ok, names = verify(manifest, broken)
    assert ok is False
    assert names == ("a.txt", "b.txt")
    assert list(names) == sorted(names)


def test_as_dict_shape() -> None:
    manifest = build_manifest({"a.txt": b"aa"})
    d = manifest.as_dict()
    assert d["schema_version"] == "1"
    assert d["total_bytes"] == 2
    assert d["root_sha256"] == manifest.root_sha256
    assert d["entries"] == [{"name": "a.txt", "sha256": sha256_hex(b"aa"), "size": 2}]


def test_to_json_stable_and_sorted_keys() -> None:
    manifest = build_manifest(_sample_files())
    first = manifest.to_json()
    second = manifest.to_json()
    assert first == second
    # sorted keys -> top-level keys appear alphabetically.
    parsed = json.loads(first)
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_to_json_round_trippable() -> None:
    manifest = build_manifest(_sample_files())
    parsed = json.loads(manifest.to_json())
    assert parsed == manifest.as_dict()
    rebuilt = PackManifest(
        entries=tuple(FileEntry(e["name"], e["sha256"], e["size"]) for e in parsed["entries"]),
        total_bytes=parsed["total_bytes"],
        root_sha256=parsed["root_sha256"],
        schema_version=parsed["schema_version"],
    )
    assert rebuilt == manifest


def test_frozen_dataclasses_immutable() -> None:
    entry = FileEntry(name="a", sha256="x", size=1)
    manifest = build_manifest({"a": b"a"})
    for target, attr, value in (
        (entry, "name", "b"),
        (manifest, "total_bytes", 99),
    ):
        try:
            setattr(target, attr, value)
        except FrozenInstanceError:
            continue
        raise AssertionError("frozen dataclass should reject mutation")
