"""Tests for the §3.6 evidence locator DTO — тесты локатора (§3.6)."""

from __future__ import annotations

from kg_common.evidence_locator import (
    EvidenceLocator,
    from_evidence,
    same_span,
    validate_locator,
)


def test_from_evidence_reads_char_end() -> None:
    loc = from_evidence(
        {"source_type": "paragraph", "doc_id": "d", "char_start": 5, "char_end": 20}
    )
    assert loc.char_end == 20
    assert loc.doc_id == "d"
    assert loc.source_type == "paragraph"


def test_from_evidence_ignores_extra_keys() -> None:
    loc = from_evidence(
        {"source_type": "paragraph", "doc_id": "d", "char_start": 1, "char_end": 2, "junk": 9}
    )
    assert loc == EvidenceLocator("d", "paragraph", char_start=1, char_end=2)


def test_from_evidence_defaults_missing_ids() -> None:
    loc = from_evidence({})
    assert loc.doc_id == ""
    assert loc.source_type == ""


def test_validate_empty_span_is_false() -> None:
    ok, errors = validate_locator(EvidenceLocator("d", "paragraph", char_start=5, char_end=5))
    assert ok is False
    assert errors


def test_validate_reversed_span_is_false() -> None:
    ok, _ = validate_locator(EvidenceLocator("d", "figure_caption", char_start=20, char_end=5))
    assert ok is False


def test_validate_good_text_span_is_true() -> None:
    assert validate_locator(EvidenceLocator("d", "paragraph", char_start=5, char_end=20)) == (
        True,
        [],
    )


def test_validate_table_cell_missing_col_is_false() -> None:
    ok, _ = validate_locator(EvidenceLocator("d", "table_cell", table_id="t", row_index=1))
    assert ok is False


def test_validate_table_cell_complete_is_true() -> None:
    assert validate_locator(
        EvidenceLocator("d", "table_cell", table_id="t", row_index=1, col_index=2)
    ) == (True, [])


def test_validate_table_cell_missing_table_id_is_false() -> None:
    ok, errors = validate_locator(EvidenceLocator("d", "table_cell", row_index=1, col_index=2))
    assert ok is False
    assert any("table_id" in e for e in errors)


def test_validate_requires_doc_id_and_source_type() -> None:
    ok, errors = validate_locator(EvidenceLocator("", "", char_start=1, char_end=2))
    assert ok is False
    assert any("doc_id" in e for e in errors)
    assert any("source_type" in e for e in errors)


def test_as_dict_omits_none_keys() -> None:
    d = EvidenceLocator("d", "paragraph", char_start=1, char_end=2).as_dict()
    assert "page" not in d
    assert "table_id" not in d
    assert d == {"doc_id": "d", "source_type": "paragraph", "char_start": 1, "char_end": 2}


def test_as_dict_keeps_present_keys() -> None:
    d = EvidenceLocator("d", "table_cell", page=3, table_id="t", row_index=1, col_index=2).as_dict()
    assert d == {
        "doc_id": "d",
        "source_type": "table_cell",
        "page": 3,
        "table_id": "t",
        "row_index": 1,
        "col_index": 2,
    }


def test_same_span_reflexive() -> None:
    loc = EvidenceLocator("d", "paragraph", char_start=5, char_end=20)
    assert same_span(loc, loc) is True


def test_same_span_differs_on_char_start() -> None:
    a = EvidenceLocator("d", "paragraph", char_start=5, char_end=20)
    b = EvidenceLocator("d", "paragraph", char_start=6, char_end=20)
    assert same_span(a, b) is False


def test_same_span_matches_distinct_equal_instances() -> None:
    a = EvidenceLocator("d", "table_cell", table_id="t", row_index=1, col_index=2)
    b = from_evidence(
        {
            "doc_id": "d",
            "source_type": "table_cell",
            "table_id": "t",
            "row_index": 1,
            "col_index": 2,
        }
    )
    assert same_span(a, b) is True


def test_key_is_stable_string() -> None:
    loc = EvidenceLocator("d", "paragraph", char_start=5, char_end=20)
    assert isinstance(loc.key(), str)
    assert loc.key() == "d|paragraph||5|20|||"
