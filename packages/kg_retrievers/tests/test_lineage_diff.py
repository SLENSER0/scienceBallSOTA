"""Tests for lineage-diff between two provenance chains (§25.17)."""

from __future__ import annotations

from kg_retrievers.lineage_diff import LineageDiff, lineage_diff


def test_added_evidence() -> None:
    """Evidence only in *after* is reported as added, not removed (§25.17)."""
    before = {"evidence_ids": ["e1"], "doc_ids": ["d1"]}
    after = {"evidence_ids": ["e1", "e2"], "doc_ids": ["d1"]}

    diff = lineage_diff(before, after)

    assert diff.added_evidence == ("e2",)
    assert diff.removed_evidence == ()
    assert diff.added_docs == ()
    assert diff.removed_docs == ()
    assert diff.is_empty is False


def test_removed_evidence() -> None:
    """Evidence only in *before* is reported as removed (§25.17)."""
    before = {"evidence_ids": ["e1", "e2", "e3"], "doc_ids": ["d1"]}
    after = {"evidence_ids": ["e2"], "doc_ids": ["d1"]}

    diff = lineage_diff(before, after)

    assert diff.removed_evidence == ("e1", "e3")
    assert diff.added_evidence == ()


def test_docs_diff() -> None:
    """Document ids diff independently of evidence ids (§25.17)."""
    before = {"evidence_ids": ["e1"], "doc_ids": ["d1", "d2"]}
    after = {"evidence_ids": ["e1"], "doc_ids": ["d2", "d3"]}

    diff = lineage_diff(before, after)

    assert diff.added_docs == ("d3",)
    assert diff.removed_docs == ("d1",)
    assert diff.added_evidence == ()
    assert diff.removed_evidence == ()


def test_no_change() -> None:
    """Identical chains (order/dupes aside) produce an empty diff (§25.17)."""
    before = {"evidence_ids": ["e2", "e1", "e1"], "doc_ids": ["d1"]}
    after = {"evidence_ids": ["e1", "e2"], "doc_ids": ["d1"]}

    diff = lineage_diff(before, after)

    assert diff == LineageDiff((), (), (), ())
    assert diff.is_empty is True


def test_empty_chains() -> None:
    """Missing keys are treated as empty; empty-vs-empty is an empty diff (§25.17)."""
    diff = lineage_diff({}, {})

    assert diff.added_evidence == ()
    assert diff.removed_evidence == ()
    assert diff.added_docs == ()
    assert diff.removed_docs == ()
    assert diff.is_empty is True


def test_symmetric() -> None:
    """Swapping before/after swaps added and removed for both collections (§25.17)."""
    a = {"evidence_ids": ["e1"], "doc_ids": ["d1"]}
    b = {"evidence_ids": ["e2"], "doc_ids": ["d2"]}

    forward = lineage_diff(a, b)
    backward = lineage_diff(b, a)

    assert forward.added_evidence == backward.removed_evidence == ("e2",)
    assert forward.removed_evidence == backward.added_evidence == ("e1",)
    assert forward.added_docs == backward.removed_docs == ("d2",)
    assert forward.removed_docs == backward.added_docs == ("d1",)


def test_as_dict() -> None:
    """``as_dict`` yields JSON-friendly lists plus the ``is_empty`` flag (§25.17)."""
    before = {"evidence_ids": ["e1", "e2"], "doc_ids": ["d1"]}
    after = {"evidence_ids": ["e2", "e3"], "doc_ids": ["d1", "d2"]}

    diff = lineage_diff(before, after)

    assert diff.as_dict() == {
        "added_evidence": ["e3"],
        "removed_evidence": ["e1"],
        "added_docs": ["d2"],
        "removed_docs": [],
        "is_empty": False,
    }
