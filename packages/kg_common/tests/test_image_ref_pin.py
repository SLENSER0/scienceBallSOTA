"""Tests for the image reference pin checker — §2.12 вендоринг/закрепление версий."""

from __future__ import annotations

from kg_common.image_ref_pin import (
    ImageRef,
    PinReport,
    check_pins,
    is_pinned,
    parse_image_ref,
)


def test_parse_plain_tag_no_registry_no_digest() -> None:
    """``neo4j:2026.05-community`` — tag only, default registry, no digest."""
    ref = parse_image_ref("neo4j:2026.05-community")
    assert ref.tag == "2026.05-community"
    assert ref.registry is None
    assert ref.digest is None
    assert ref.repository == "neo4j"


def test_parse_registry_and_namespaced_repository() -> None:
    """A dotted first segment is the registry; the rest is the repository path."""
    ref = parse_image_ref("quay.io/docling-project/docling-serve:latest")
    assert ref.registry == "quay.io"
    assert ref.repository == "docling-project/docling-serve"
    assert ref.tag == "latest"
    assert ref.digest is None


def test_parse_digest_is_pinned() -> None:
    """A ``@sha256:…`` digest is captured and always counts as pinned."""
    ref = parse_image_ref("postgres@sha256:abc")
    assert ref.digest == "sha256:abc"
    assert ref.repository == "postgres"
    assert ref.tag is None
    assert is_pinned(ref) is True


def test_latest_tag_is_not_pinned() -> None:
    """A floating ``:latest`` tag is never pinned."""
    assert is_pinned(parse_image_ref("qdrant/qdrant:latest")) is False


def test_bare_repository_has_no_tag_and_is_not_pinned() -> None:
    """``redis`` with no tag and no digest is unpinned."""
    ref = parse_image_ref("redis")
    assert ref.tag is None
    assert ref.digest is None
    assert ref.registry is None
    assert is_pinned(ref) is False


def test_check_pins_reports_unpinned_and_not_ok() -> None:
    """A mix of pinned and floating images yields the unpinned pair and ok=False."""
    report = check_pins({"a": "redis:7", "b": "q:latest"})
    assert report.unpinned == (("b", "q:latest"),)
    assert report.ok is False
    assert report.pinned == ("a",)


def test_concrete_tag_is_pinned() -> None:
    """A non-latest tag counts as pinned even without a digest."""
    assert is_pinned(parse_image_ref("redis:7")) is True


def test_bare_repo_with_namespace_no_registry() -> None:
    """A first segment without ``.``/``:`` stays part of the repository path."""
    ref = parse_image_ref("qdrant/qdrant:latest")
    assert ref.registry is None
    assert ref.repository == "qdrant/qdrant"
    assert ref.tag == "latest"


def test_registry_with_port_not_split_as_tag() -> None:
    """A registry ``host:port`` is not mistaken for a repository ``:tag``."""
    ref = parse_image_ref("localhost:5000/team/app:1.2.3")
    assert ref.registry == "localhost:5000"
    assert ref.repository == "team/app"
    assert ref.tag == "1.2.3"


def test_registry_repo_tag_and_digest_together() -> None:
    """All four components parse independently when present."""
    ref = parse_image_ref("quay.io/ns/app:1.0@sha256:deadbeef")
    assert ref.registry == "quay.io"
    assert ref.repository == "ns/app"
    assert ref.tag == "1.0"
    assert ref.digest == "sha256:deadbeef"
    assert is_pinned(ref) is True


def test_imageref_as_dict_roundtrip() -> None:
    """:meth:`ImageRef.as_dict` is a plain JSON-friendly view."""
    ref = ImageRef(registry="quay.io", repository="ns/app", tag="1.0", digest=None)
    assert ref.as_dict() == {
        "registry": "quay.io",
        "repository": "ns/app",
        "tag": "1.0",
        "digest": None,
    }


def test_all_pinned_report_is_ok() -> None:
    """When every image is pinned the report is ok with empty unpinned."""
    report = check_pins({"a": "redis:7", "b": "pg@sha256:abc"})
    assert report.ok is True
    assert report.unpinned == ()
    assert report.pinned == ("a", "b")


def test_pinreport_as_dict_shape() -> None:
    """:meth:`PinReport.as_dict` lists pairs and preserves ``ok``."""
    report = PinReport(unpinned=(("b", "q:latest"),), pinned=("a",), ok=False)
    assert report.as_dict() == {
        "unpinned": [["b", "q:latest"]],
        "pinned": ["a"],
        "ok": False,
    }


def test_check_pins_preserves_order() -> None:
    """Unpinned pairs follow the input mapping order."""
    report = check_pins({"x": "a:latest", "y": "b:1", "z": "c"})
    assert report.unpinned == (("x", "a:latest"), ("z", "c"))
    assert report.pinned == ("y",)
