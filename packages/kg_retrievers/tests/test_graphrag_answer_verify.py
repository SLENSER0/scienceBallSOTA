"""Tests for GraphRAG answer verification (§11.13)."""

from __future__ import annotations

import json

from kg_retrievers.graphrag_answer_verify import (
    AnswerCheck,
    extract_numbers,
    verify_answer,
)


def test_supported_number_not_flagged() -> None:
    """(1) '320 MPa' backed by a source with '320 MPa' -> nothing unsupported."""
    check = verify_answer(
        "The yield strength is 320 MPa.",
        source_texts=["Measured yield strength was 320 MPa in tension."],
        cited_doc_ids=["d1"],
        answer_doc_ids=[],
    )
    assert check.unsupported_numbers == ()
    assert "320 MPa" in check.numeric_claims
    assert check.ok is True


def test_unsupported_number_flagged() -> None:
    """(2) '999 MPa' with no matching source -> '999' unsupported, ok False."""
    check = verify_answer(
        "It reaches 999 MPa.",
        source_texts=["Reported values cluster near 320 MPa."],
        cited_doc_ids=["d1"],
        answer_doc_ids=[],
    )
    assert "999" in check.unsupported_numbers
    assert check.ok is False


def test_unknown_citation_flagged() -> None:
    """(3) answer_doc_ids=['dX'] absent from cited -> 'dX' unknown, ok False."""
    check = verify_answer(
        "See the reference.",
        source_texts=["Any supporting text."],
        cited_doc_ids=["d1", "d2"],
        answer_doc_ids=["dX"],
    )
    assert "dX" in check.unknown_citations
    assert check.ok is False


def test_fully_supported_answer_ok() -> None:
    """(4) grounded numbers and known citations -> ok True."""
    check = verify_answer(
        "Hardness of 148 HV was seen in d2.",
        source_texts=["Vickers hardness reached 148 HV.", "context of 320 MPa"],
        cited_doc_ids=["d1", "d2"],
        answer_doc_ids=["d2"],
    )
    assert check.ok is True
    assert check.unsupported_numbers == ()
    assert check.unknown_citations == ()


def test_extract_numbers_range_and_unit() -> None:
    """(5) 'extract_numbers' captures both magnitudes of range + separate value."""
    tokens = extract_numbers("12-28 % and 148 HV")
    assert tokens == ["12-28 %", "148 HV"]


def test_answer_without_numbers_ok_depends_on_citations() -> None:
    """(6) no numbers -> numeric_claims empty; ok driven only by citations."""
    good = verify_answer(
        "This alloy is widely studied.",
        source_texts=["Background text with no digits."],
        cited_doc_ids=["d1"],
        answer_doc_ids=["d1"],
    )
    assert good.numeric_claims == ()
    assert good.ok is True

    bad = verify_answer(
        "This alloy is widely studied.",
        source_texts=["Background text with no digits."],
        cited_doc_ids=["d1"],
        answer_doc_ids=["dZ"],
    )
    assert bad.numeric_claims == ()
    assert bad.unknown_citations == ("dZ",)
    assert bad.ok is False


def test_as_dict_json_roundtrips() -> None:
    """(7) 'as_dict' produces a JSON-serialisable, faithfully restorable payload."""
    check = verify_answer(
        "Value 999 MPa cited in dX.",
        source_texts=["Only 320 MPa here."],
        cited_doc_ids=["d1"],
        answer_doc_ids=["dX"],
    )
    payload = check.as_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["ok"] is False
    assert decoded["unsupported_numbers"] == ["999"]
    assert decoded["unknown_citations"] == ["dX"]

    restored = AnswerCheck(
        ok=decoded["ok"],
        numeric_claims=tuple(decoded["numeric_claims"]),
        unsupported_numbers=tuple(decoded["unsupported_numbers"]),
        unknown_citations=tuple(decoded["unknown_citations"]),
    )
    assert restored == check
