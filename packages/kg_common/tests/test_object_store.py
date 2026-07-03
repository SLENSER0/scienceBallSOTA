"""Local object store (§5.5): S3-like blob storage over the local FS."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Iterator

import pytest

from kg_common.storage.object_store import ObjectRef, ObjectStore


@pytest.fixture
def store() -> Iterator[ObjectStore]:
    root = tempfile.mkdtemp(prefix="objstore-")
    try:
        yield ObjectStore(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_put_get_round_trip(store: ObjectStore) -> None:
    data = "Отчёт: проба руды\n".encode()
    ref = store.put("raw", "reports/a.txt", data)
    assert isinstance(ref, ObjectRef)
    assert ref.bucket == "raw"
    assert ref.key == "reports/a.txt"
    assert ref.size == len(data)
    assert ref.sha256 == hashlib.sha256(data).hexdigest()
    assert store.get("raw", "reports/a.txt") == data


def test_exists_true_and_false(store: ObjectStore) -> None:
    store.put("raw", "k1", b"x")
    assert store.exists("raw", "k1") is True
    assert store.exists("raw", "missing") is False
    assert store.exists("nobucket", "k1") is False


def test_object_ref_as_dict(store: ObjectStore) -> None:
    ref = store.put("raw", "k", b"abc")
    assert ref.as_dict() == {
        "bucket": "raw",
        "key": "k",
        "size": 3,
        "sha256": hashlib.sha256(b"abc").hexdigest(),
    }


def test_put_content_is_content_addressed_and_dedups(store: ObjectStore) -> None:
    data = b"identical-bytes"
    key1 = store.put_content("cas", data)
    key2 = store.put_content("cas", data)
    assert key1 == key2 == hashlib.sha256(data).hexdigest()
    assert len(key1) == 64
    assert store.get("cas", key1) == data
    # Deduped: identical content collapses to a single blob.
    assert store.list("cas") == [key1]


def test_list_with_prefix(store: ObjectStore) -> None:
    store.put("b", "docs/1.txt", b"1")
    store.put("b", "docs/2.txt", b"2")
    store.put("b", "img/3.bin", b"3")
    assert store.list("b", prefix="docs/") == ["docs/1.txt", "docs/2.txt"]
    assert store.list("b") == ["docs/1.txt", "docs/2.txt", "img/3.bin"]


def test_delete(store: ObjectStore) -> None:
    store.put("b", "k", b"v")
    assert store.delete("b", "k") is True
    assert store.exists("b", "k") is False
    assert store.delete("b", "k") is False  # idempotent: absent -> False


def test_path_traversal_rejected(store: ObjectStore) -> None:
    with pytest.raises(ValueError):
        store.put("b", "../x", b"bad")
    with pytest.raises(ValueError):
        store.get("b", "../../etc/passwd")
    with pytest.raises(ValueError):
        store.put("b", "/abs/key", b"bad")


def test_write_and_read_manifest(store: ObjectStore) -> None:
    entries = {
        "a.txt": {"size": 3, "sha256": "deadbeef"},
        "версия": 1,
    }
    ref = store.write_manifest("exports", entries)
    assert isinstance(ref, ObjectRef)
    assert ref.key == "manifest.json"
    assert store.read_manifest("exports") == entries


def test_empty_bucket_list(store: ObjectStore) -> None:
    assert store.list("never-created") == []
