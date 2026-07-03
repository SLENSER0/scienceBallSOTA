"""Tests for GraphRAG inline citation formatting (§11.11).

Hand-checkable assertions on ``format_citation`` / ``annotate_answer`` /
``extract_report_ids`` and ``CitedAnswer.as_dict``.
"""

from __future__ import annotations

from kg_retrievers.graphrag_answer_citations import (
    CitedAnswer,
    annotate_answer,
    extract_report_ids,
    format_citation,
)


def test_format_citation_sorted_deduped() -> None:
    assert format_citation([5, 1, 1]) == "[Data: Reports (1, 5)]"


def test_format_citation_basic_order() -> None:
    assert format_citation([8, 1, 5]) == "[Data: Reports (1, 5, 8)]"


def test_format_citation_empty() -> None:
    assert format_citation([]) == ""


def test_annotate_appends_marker() -> None:
    ans = annotate_answer("The graphene sheet is stable.", [5, 1], ["doc-b", "doc-a"])
    marker = "[Data: Reports (1, 5)]"
    assert ans.text.endswith(marker)
    assert ans.text == "The graphene sheet is stable. " + marker
    assert ans.report_ids == (1, 5)
    assert ans.doc_ids == ("doc-a", "doc-b")


def test_annotate_no_ids_leaves_text_unchanged() -> None:
    ans = annotate_answer("No sources here.", [], [])
    assert ans.text == "No sources here."
    assert "[Data: Reports" not in ans.text
    assert ans.report_ids == ()
    assert ans.doc_ids == ()


def test_extract_round_trip() -> None:
    ans = annotate_answer("Finding.", [1, 5], ["d1"])
    assert extract_report_ids(ans.text) == [1, 5]


def test_extract_two_markers_merged_sorted() -> None:
    text = "Alpha [Data: Reports (5, 8)] and beta [Data: Reports (1, 5)]."
    assert extract_report_ids(text) == [1, 5, 8]


def test_extract_no_marker() -> None:
    assert extract_report_ids("plain text, no citation") == []


def test_doc_ids_sorted_deduped() -> None:
    ans = annotate_answer("X.", [2], ["z", "a", "a", "m"])
    assert ans.doc_ids == ("a", "m", "z")


def test_as_dict_returns_lists() -> None:
    ans = CitedAnswer(text="hi", report_ids=(1, 2), doc_ids=("d1", "d2"))
    d = ans.as_dict()
    assert d == {"text": "hi", "report_ids": [1, 2], "doc_ids": ["d1", "d2"]}
    assert isinstance(d["report_ids"], list)
    assert isinstance(d["doc_ids"], list)
