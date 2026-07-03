"""Tests for the citation existence / phantom-citation check (§18.10)."""

from __future__ import annotations

from kg_eval.citation_check import CitationCheckResult, check_citations


def test_all_cited_in_known_no_required() -> None:
    """All cited resolve, nothing required -> ok, no phantom, precision 1.0."""
    res = check_citations(["e1", "e2"], ["e1", "e2", "e3"])
    assert res.ok is True
    assert res.phantom == ()
    assert res.missing_required == ()
    assert res.precision == 1.0
    assert res.cited == ("e1", "e2")


def test_phantom_citation_half_precision() -> None:
    """cited ['e1','e9'] known ['e1'] -> phantom ('e9',), precision 0.5, not ok."""
    res = check_citations(["e1", "e9"], ["e1"])
    assert res.phantom == ("e9",)
    assert res.precision == 0.5
    assert res.ok is False


def test_missing_required_fails() -> None:
    """required ['e2'] not cited -> missing_required ('e2',), ok False."""
    res = check_citations(["e1"], ["e1", "e2"], required_ids=["e2"])
    assert res.missing_required == ("e2",)
    assert res.ok is False
    # e1 is a real citation, so precision is still perfect.
    assert res.precision == 1.0


def test_duplicate_cited_deduped() -> None:
    """duplicate cited ['e1','e1'] deduped to one, precision stays 1.0."""
    res = check_citations(["e1", "e1"], ["e1"])
    assert res.cited == ("e1",)
    assert res.precision == 1.0
    assert res.ok is True


def test_empty_cited_precision_one() -> None:
    """empty cited -> precision 1.0, ok True when nothing is required."""
    res = check_citations([], ["e1", "e2"])
    assert res.cited == ()
    assert res.phantom == ()
    assert res.precision == 1.0
    assert res.ok is True


def test_empty_cited_but_required_fails() -> None:
    """empty cited with a required id -> missing_required, ok False."""
    res = check_citations([], ["e1"], required_ids=["e1"])
    assert res.missing_required == ("e1",)
    assert res.ok is False
    assert res.precision == 1.0


def test_phantom_tuple_is_sorted() -> None:
    """phantom tuple comes back sorted regardless of input order."""
    res = check_citations(["e9", "e2", "e5"], ["e1"])
    assert res.phantom == ("e2", "e5", "e9")


def test_as_dict_types_and_rounding() -> None:
    """as_dict()['ok'] is a bool and precision is rounded to a float."""
    res = check_citations(["e1", "e2", "e9"], ["e1", "e2"])
    d = res.as_dict()
    assert isinstance(d["ok"], bool)
    assert d["ok"] is False
    # 2/3 -> rounded to 6 places.
    assert d["precision"] == round(2 / 3, 6)
    assert isinstance(d["precision"], float)
    assert d["phantom"] == ["e9"]


def test_result_is_frozen() -> None:
    """CitationCheckResult is frozen and cannot be mutated."""
    res = check_citations(["e1"], ["e1"])
    assert isinstance(res, CitationCheckResult)
    try:
        res.ok = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("CitationCheckResult should be frozen")
