"""Tests for the artifact/data versioning abstraction (§10.13)."""

from __future__ import annotations

import hashlib

import pytest

from kg_common.metadata.artifact_versioning import (
    DataVersion,
    NoopVersioner,
    compute_version_ref,
    make_versioner,
)


def test_compute_version_ref_deterministic_and_length() -> None:
    # Same (path, message) → same ref, and the ref is exactly 12 hex chars.
    assert compute_version_ref("/a", "m") == compute_version_ref("/a", "m")
    assert len(compute_version_ref("/a", "m")) == 12


def test_compute_version_ref_matches_sha256_prefix() -> None:
    # The ref is the first 12 hex chars of sha256(path + '\x1f' + message).
    expected = hashlib.sha256(b"/a\x1fm").hexdigest()[:12]
    assert compute_version_ref("/a", "m") == expected


def test_compute_version_ref_message_changes_ref() -> None:
    assert compute_version_ref("/a", "m") != compute_version_ref("/a", "n")


def test_compute_version_ref_path_changes_ref() -> None:
    assert compute_version_ref("/a", "m") != compute_version_ref("/b", "m")


def test_compute_version_ref_is_hex() -> None:
    ref = compute_version_ref("/kg-raw/x", "ingest")
    assert all(c in "0123456789abcdef" for c in ref)


def test_noop_versioner_commit() -> None:
    v = NoopVersioner().commit("/kg-raw/x", "ingest")
    assert v.backend == "none"
    assert v.ref == compute_version_ref("/kg-raw/x", "ingest")
    assert v.path == "/kg-raw/x"
    assert v.message == "ingest"


def test_noop_versioner_commit_default_message() -> None:
    v = NoopVersioner().commit("/kg-raw/x")
    assert v.message == ""
    assert v.ref == compute_version_ref("/kg-raw/x", "")


def test_data_version_as_dict() -> None:
    v = NoopVersioner().commit("/kg-raw/x", "ingest")
    assert v.as_dict() == {
        "backend": "none",
        "ref": compute_version_ref("/kg-raw/x", "ingest"),
        "path": "/kg-raw/x",
        "message": "ingest",
    }
    assert v.as_dict()["path"] == "/kg-raw/x"


def test_data_version_frozen() -> None:
    v = DataVersion(backend="none", ref="abc", path="/p", message="m")
    with pytest.raises(AttributeError):
        v.ref = "other"  # type: ignore[misc]


def test_make_versioner_none() -> None:
    assert isinstance(make_versioner("none"), NoopVersioner)
    # Default argument is 'none'.
    assert isinstance(make_versioner(), NoopVersioner)


def test_make_versioner_lakefs_rejected() -> None:
    with pytest.raises(ValueError, match="not embeddable"):
        make_versioner("lakefs")


def test_make_versioner_dvc_rejected() -> None:
    with pytest.raises(ValueError, match="not embeddable"):
        make_versioner("dvc")


def test_make_versioner_unknown_rejected() -> None:
    with pytest.raises(ValueError):
        make_versioner("bogus")
