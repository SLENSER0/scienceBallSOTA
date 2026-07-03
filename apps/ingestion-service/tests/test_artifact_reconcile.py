"""Tests for §5.5 idempotent re-ingest reconciliation and orphan cleanup.

Тесты сверки артефактов при переингестии (§5.5).
"""

from __future__ import annotations

from ingestion_service.artifact_reconcile import (
    ReconcilePlan,
    is_doc_prefixed,
    reconcile_artifacts,
)


def test_reconcile_basic_split() -> None:
    """keep = shared, delete = orphan, create = new (hand-checked example)."""
    plan = reconcile_artifacts(["a/x", "a/old"], ["a/x", "a/new"])
    assert plan.keep == ("a/x",)
    assert plan.delete == ("a/old",)
    assert plan.create == ("a/new",)


def test_reconcile_no_overlap() -> None:
    """keep, delete and create partition the key space with no overlaps."""
    plan = reconcile_artifacts(["a/x", "a/old"], ["a/x", "a/new"])
    keep, delete, create = set(plan.keep), set(plan.delete), set(plan.create)
    assert keep & delete == set()
    assert keep & create == set()
    assert delete & create == set()


def test_reconcile_identical_inputs_all_kept() -> None:
    """Identical inputs => nothing to delete or create, everything kept."""
    keys = ["a/x", "a/y", "a/z"]
    plan = reconcile_artifacts(keys, list(keys))
    assert plan.keep == ("a/x", "a/y", "a/z")
    assert plan.delete == ()
    assert plan.create == ()


def test_reconcile_empty_existing_creates_all() -> None:
    """Empty store => nothing to delete, create equals the whole manifest."""
    plan = reconcile_artifacts([], ["a/x", "a/y"])
    assert plan.delete == ()
    assert plan.create == ("a/x", "a/y")
    assert plan.keep == ()


def test_reconcile_empty_manifest_deletes_all() -> None:
    """Empty manifest => every existing key is an orphan to delete."""
    plan = reconcile_artifacts(["a/x", "a/y"], [])
    assert plan.delete == ("a/x", "a/y")
    assert plan.create == ()
    assert plan.keep == ()


def test_reconcile_outputs_sorted() -> None:
    """All three tuples come back sorted regardless of input order."""
    plan = reconcile_artifacts(["b", "a", "gone2", "gone1"], ["b", "a", "new2", "new1"])
    assert plan.keep == ("a", "b")
    assert plan.delete == ("gone1", "gone2")
    assert plan.create == ("new1", "new2")


def test_reconcile_dedupes_via_set() -> None:
    """Duplicate input keys collapse (set semantics)."""
    plan = reconcile_artifacts(["a", "a", "a"], ["a", "a"])
    assert plan.keep == ("a",)
    assert plan.delete == ()
    assert plan.create == ()


def test_is_doc_prefixed_true() -> None:
    """A key under the document's own prefix is accepted."""
    assert is_doc_prefixed("documents/doc:5/document.md", "5") is True


def test_is_doc_prefixed_false_other_doc() -> None:
    """A key under a different document's prefix is rejected."""
    assert is_doc_prefixed("documents/doc:9/x", "5") is False


def test_is_doc_prefixed_rejects_partial_id_match() -> None:
    """doc:5 must not match doc:55 (prefix boundary is the trailing slash)."""
    assert is_doc_prefixed("documents/doc:55/x", "5") is False


def test_as_dict_shape_and_values() -> None:
    """as_dict() returns plain sorted lists under keep/delete/create."""
    plan = reconcile_artifacts(["a/x", "a/old"], ["a/x", "a/new"])
    d = plan.as_dict()
    assert d["delete"] == ["a/old"]
    assert d["keep"] == ["a/x"]
    assert d["create"] == ["a/new"]
    assert isinstance(d["keep"], list)


def test_plan_is_frozen() -> None:
    """ReconcilePlan is immutable (frozen dataclass)."""
    plan = ReconcilePlan(keep=("a",), delete=(), create=())
    try:
        plan.keep = ("b",)  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ReconcilePlan should be frozen")
