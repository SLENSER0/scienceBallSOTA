"""Tests for the compose volume/network reference validator (§2.5)."""

from __future__ import annotations

from kg_common.compose_resource_refs import (
    ResourceRefReport,
    check_refs,
    referenced_volumes,
)


def test_referenced_volumes_named_volume() -> None:
    """A ``name:/path`` entry contributes the volume name; a bind mount is excluded."""
    services = {"neo4j": {"volumes": ["neo4j-data:/data", "./src:/app"]}}
    assert referenced_volumes(services) == frozenset({"neo4j-data"})


def test_referenced_volumes_bind_mount_excluded() -> None:
    """Bind mounts starting with '.' or '/' are excluded, not treated as names."""
    services = {"app": {"volumes": ["./src:/app", "/host/data:/container"]}}
    assert referenced_volumes(services) == frozenset()


def test_referenced_volumes_multiple_services() -> None:
    """Named volumes are unioned across all services."""
    services = {
        "neo4j": {"volumes": ["neo4j-data:/data", "./conf:/conf"]},
        "qdrant": {"volumes": ["qdrant-store:/qdrant/storage"]},
        "web": {"ports": ["8080:80"]},  # no volumes key at all
    }
    assert referenced_volumes(services) == frozenset({"neo4j-data", "qdrant-store"})


def test_referenced_volumes_anonymous_mount_ignored() -> None:
    """An entry with no ':' (anonymous volume) contributes no name."""
    services = {"cache": {"volumes": ["/var/cache"]}}
    # '/var/cache' has no ':' and would be a bind-source anyway → excluded.
    assert referenced_volumes(services) == frozenset()

    services2 = {"cache": {"volumes": ["cache-data"]}}
    # 'cache-data' bare, no ':' → anonymous, no reference recorded.
    assert referenced_volumes(services2) == frozenset()


def test_check_refs_undeclared_fails() -> None:
    """A referenced-but-undeclared name lands in ``undeclared`` and fails the gate."""
    report = check_refs(["a", "b"], ["a"])
    assert report.undeclared == ("b",)
    assert report.unused == ()
    assert report.ok is False


def test_check_refs_unused_is_warning() -> None:
    """A declared-but-unused name lands in ``unused`` but does not fail the gate."""
    report = check_refs(["a"], ["a", "b"])
    assert report.unused == ("b",)
    assert report.undeclared == ()
    assert report.ok is True


def test_check_refs_empty_referenced() -> None:
    """No references but one declaration → that name is unused, still ok."""
    report = check_refs([], ["x"])
    assert report.unused == ("x",)
    assert report.undeclared == ()
    assert report.ok is True


def test_check_refs_all_matched() -> None:
    """Exact match → both tuples empty, ok True."""
    report = check_refs(["a", "b"], ["b", "a"])
    assert report.undeclared == ()
    assert report.unused == ()
    assert report.ok is True


def test_check_refs_undeclared_sorted() -> None:
    """The ``undeclared`` tuple is sorted deterministically."""
    report = check_refs(["z", "a", "m"], [])
    assert report.undeclared == ("a", "m", "z")


def test_check_refs_unused_sorted() -> None:
    """The ``unused`` tuple is sorted deterministically."""
    report = check_refs([], ["z", "a", "m"])
    assert report.unused == ("a", "m", "z")


def test_as_dict_ok_is_bool() -> None:
    """``as_dict()['ok']`` is a plain bool suitable for JSON serialisation."""
    report = check_refs(["a"], ["a"])
    d = report.as_dict()
    assert isinstance(d["ok"], bool)
    assert d == {"undeclared": [], "unused": [], "ok": True}


def test_as_dict_full_shape() -> None:
    """``as_dict()`` reflects both difference lists and the ok flag."""
    report = check_refs(["a", "b"], ["a", "c"])
    assert report.as_dict() == {"undeclared": ["b"], "unused": ["c"], "ok": False}


def test_report_is_frozen() -> None:
    """The report dataclass is immutable — frozen guarantees stable outputs."""
    report = ResourceRefReport(undeclared=(), unused=(), ok=True)
    try:
        report.ok = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen must raise
        raise AssertionError("ResourceRefReport should be frozen")


def test_end_to_end_referenced_then_check() -> None:
    """Wire referenced_volumes into check_refs against a declaration block."""
    services = {
        "neo4j": {"volumes": ["neo4j-data:/data", "./src:/app"]},
        "qdrant": {"volumes": ["qdrant-store:/qdrant/storage"]},
    }
    referenced = referenced_volumes(services)
    # Declared block forgot 'qdrant-store' and over-declared 'stale-vol'.
    report = check_refs(referenced, ["neo4j-data", "stale-vol"])
    assert report.undeclared == ("qdrant-store",)
    assert report.unused == ("stale-vol",)
    assert report.ok is False
