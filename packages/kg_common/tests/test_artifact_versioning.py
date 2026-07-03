"""Tests for content-addressed artifact versioning — тесты (§10.13)."""

from __future__ import annotations

import hashlib

import pytest

from kg_common.artifact_versioning import (
    ArtifactVersion,
    NoopVersioner,
    Versioner,
    make_versioner,
)


def test_version_id_is_short_sha256_prefix() -> None:
    """``version_id`` == first 12 hex chars of the SHA-256 of the bytes."""
    version = NoopVersioner().commit("s3://kg-raw/a", b"hello", "t0")
    assert version.version_id == hashlib.sha256(b"hello").hexdigest()[:12]
    assert len(version.version_id) == 12


def test_commit_sets_uri_and_full_content_hash() -> None:
    """``commit`` preserves the input URI and stores the full 64-char digest."""
    version = NoopVersioner().commit("s3://kg-raw/a", b"hello", "t0")
    assert version.uri == "s3://kg-raw/a"
    assert version.content_hash == hashlib.sha256(b"hello").hexdigest()
    assert len(version.content_hash) == 64
    assert version.created_at == "t0"


def test_same_content_twice_equal_hash_two_entries() -> None:
    """Identical bytes hash identically yet yield two distinct history entries."""
    v = NoopVersioner()
    first = v.commit("s3://kg-raw/a", b"hello", "t0")
    second = v.commit("s3://kg-raw/a", b"hello", "t1")
    assert first.content_hash == second.content_hash
    assert first.version_id == second.version_id
    history = v.history("s3://kg-raw/a")
    assert len(history) == 2
    assert history == (first, second)


def test_latest_returns_most_recent_commit() -> None:
    """``latest`` returns the last-committed version for a URI."""
    v = NoopVersioner()
    v.commit("s3://kg-raw/a", b"one", "t0")
    newest = v.commit("s3://kg-raw/a", b"two", "t1")
    assert v.latest("s3://kg-raw/a") == newest
    assert v.latest("s3://kg-raw/a").content_hash == hashlib.sha256(b"two").hexdigest()


def test_history_and_latest_for_unseen_uri() -> None:
    """An unknown URI has an empty history and ``None`` latest."""
    v = NoopVersioner()
    assert v.history("unseen") == ()
    assert v.latest("unseen") is None


def test_make_versioner_none_returns_noop() -> None:
    """The ``none`` kind (default) builds an embeddable :class:`NoopVersioner`."""
    made = make_versioner("none")
    assert isinstance(made, NoopVersioner)
    assert isinstance(make_versioner(), NoopVersioner)
    assert isinstance(made, Versioner)


@pytest.mark.parametrize("kind", ["lakefs", "dvc"])
def test_make_versioner_rejects_remote_backends(kind: str) -> None:
    """Remote backends are declared but not embeddable — raise ``ValueError``."""
    with pytest.raises(ValueError):
        make_versioner(kind)


def test_make_versioner_lakefs_direct_call() -> None:
    """The lakefs backend is unavailable and raises ``ValueError``."""
    with pytest.raises(ValueError):
        make_versioner("lakefs")


def test_make_versioner_unknown_kind() -> None:
    """An unrecognized kind raises ``ValueError``."""
    with pytest.raises(ValueError):
        make_versioner("git-annex")


def test_as_dict_shape_and_content_hash_length() -> None:
    """``as_dict`` exposes all four fields; ``content_hash`` is 64 hex chars."""
    version = NoopVersioner().commit("s3://kg-raw/a", b"hello", "t0")
    d = version.as_dict()
    assert set(d) == {"uri", "version_id", "content_hash", "created_at"}
    assert len(d["content_hash"]) == 64
    assert d["uri"] == "s3://kg-raw/a"
    assert d["version_id"] == hashlib.sha256(b"hello").hexdigest()[:12]


def test_artifact_version_is_frozen() -> None:
    """:class:`ArtifactVersion` is immutable — frozen dataclass."""
    version = ArtifactVersion("u", "vid", "h", "t0")
    with pytest.raises((AttributeError, TypeError)):
        version.uri = "other"  # type: ignore[misc]


def test_separate_uris_isolated_histories() -> None:
    """Commits under different URIs keep independent histories."""
    v = NoopVersioner()
    a = v.commit("s3://kg-raw/a", b"aaa", "t0")
    b = v.commit("s3://kg-raw/b", b"bbb", "t1")
    assert v.history("s3://kg-raw/a") == (a,)
    assert v.history("s3://kg-raw/b") == (b,)
    assert v.latest("s3://kg-raw/a") == a
    assert v.latest("s3://kg-raw/b") == b
