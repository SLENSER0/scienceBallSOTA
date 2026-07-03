"""Tests for §5.12 source-dedup report — hand-checked grouping by content hash.

Documents are ``{id, content_hash}`` dicts. Grouping is by ``content_hash`` in
first-seen order; the first id per hash is kept, later ones are dropped
duplicates. Fixtures below fix concrete ids/hashes so every expected value is
hand-checkable.
"""

from __future__ import annotations

from kg_extractors.dedup_report import DedupReport, build_dedup_report


def _docs() -> list[dict[str, str]]:
    """Batch of 4 docs: hash "aa" ×3 (d1 kept, d2/d3 dropped), hash "bb" ×1."""
    return [
        {"id": "d1", "content_hash": "aa"},
        {"id": "d2", "content_hash": "aa"},
        {"id": "d3", "content_hash": "aa"},
        {"id": "d4", "content_hash": "bb"},
    ]


def test_duplicates_grouped_by_hash() -> None:
    """by_hash groups every id sharing a content_hash, in input order (§5.12)."""
    report = build_dedup_report(_docs())
    assert isinstance(report, DedupReport)
    assert report.by_hash["aa"] == ["d1", "d2", "d3"]
    assert report.by_hash["bb"] == ["d4"]


def test_unique_count() -> None:
    """unique == number of distinct content_hash values (2: "aa", "bb")."""
    report = build_dedup_report(_docs())
    assert report.total == 4
    assert report.unique == 2
    # dropped duplicates = total - unique = 4 - 2 = 2 (hand-checked).
    assert len(report.duplicates) == report.total - report.unique


def test_duplicate_pairs_kept_dropped() -> None:
    """duplicate_pairs expands groups into (kept, dropped) rows (§5.12)."""
    report = build_dedup_report(_docs())
    # "aa": kept d1, dropped d2 and d3 → two pairs; "bb": no duplicate.
    assert report.duplicate_pairs() == [("d1", "d2"), ("d1", "d3")]


def test_duplicates_are_dropped_ids() -> None:
    """duplicates lists exactly the dropped ids (non-first per hash), in order."""
    report = build_dedup_report(_docs())
    assert report.duplicates == ["d2", "d3"]
    assert report.has_duplicates is True


def test_no_duplicates_case() -> None:
    """All-distinct hashes → no duplicates, unique == total, empty pairs (§5.12)."""
    docs = [
        {"id": "a", "content_hash": "h1"},
        {"id": "b", "content_hash": "h2"},
        {"id": "c", "content_hash": "h3"},
    ]
    report = build_dedup_report(docs)
    assert report.total == 3
    assert report.unique == 3
    assert report.duplicates == []
    assert report.has_duplicates is False
    assert report.duplicate_pairs() == []
    assert report.by_hash == {"h1": ["a"], "h2": ["b"], "h3": ["c"]}


def test_empty_returns_zeros() -> None:
    """Empty input → all-zero report with empty collections (§5.12)."""
    report = build_dedup_report([])
    assert report.total == 0
    assert report.unique == 0
    assert report.duplicates == []
    assert report.by_hash == {}
    assert report.duplicate_pairs() == []
    assert report.has_duplicates is False


def test_by_hash_mapping_preserves_first_seen_order() -> None:
    """by_hash keys follow first-seen hash order even when duplicates interleave."""
    docs = [
        {"id": "x", "content_hash": "bb"},
        {"id": "y", "content_hash": "aa"},
        {"id": "z", "content_hash": "bb"},
    ]
    report = build_dedup_report(docs)
    assert list(report.by_hash.keys()) == ["bb", "aa"]
    assert report.by_hash == {"bb": ["x", "z"], "aa": ["y"]}
    assert report.duplicates == ["z"]
    assert report.duplicate_pairs() == [("x", "z")]


def test_as_dict() -> None:
    """as_dict is the full JSON-friendly view of every field (§5.12)."""
    report = build_dedup_report(_docs())
    assert report.as_dict() == {
        "total": 4,
        "unique": 2,
        "duplicates": ["d2", "d3"],
        "by_hash": {"aa": ["d1", "d2", "d3"], "bb": ["d4"]},
    }


def test_as_dict_is_deep_copied() -> None:
    """as_dict returns copies — mutating it never touches the frozen report."""
    report = build_dedup_report(_docs())
    dumped = report.as_dict()
    dumped["duplicates"].append("tampered")  # type: ignore[union-attr]
    dumped["by_hash"]["aa"].append("tampered")  # type: ignore[index]
    assert report.duplicates == ["d2", "d3"]
    assert report.by_hash["aa"] == ["d1", "d2", "d3"]
