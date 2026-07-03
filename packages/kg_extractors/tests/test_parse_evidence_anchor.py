"""Parse-time evidence anchor stub tests — §5.7 / §8.3.

Hand-checked expectations over the three surface builders. We prove that each
builder tags its ``source_type`` correctly, that ``as_dict`` names only the
coordinates that surface uses (a paragraph anchor has no ``table_id`` key; a
table-cell anchor has no ``char_start`` key), that ``None``-valued fields are
dropped, and that malformed spans / negative table coordinates raise
``ValueError``. No extractor / model / confidence field ever appears — those are
§6 provenance, not parse-time location.
"""

from __future__ import annotations

import pytest

from kg_extractors.parse_evidence_anchor import (
    EvidenceAnchor,
    anchor_for_caption,
    anchor_for_paragraph,
    anchor_for_table_cell,
)


def test_paragraph_source_type_and_no_table_key() -> None:
    a = anchor_for_paragraph("doc-1", page=3, char_start=100, char_end=142)
    assert a.source_type == "paragraph"
    assert a.doc_id == "doc-1"
    assert a.page == 3
    assert (a.char_start, a.char_end) == (100, 142)
    d = a.as_dict()
    # Prose surface: no table coordinates appear at all.
    assert "table_id" not in d
    assert "row_index" not in d
    assert "col_index" not in d
    assert d == {
        "doc_id": "doc-1",
        "source_type": "paragraph",
        "page": 3,
        "char_start": 100,
        "char_end": 142,
    }


def test_table_cell_coords_set_and_char_offsets_none() -> None:
    a = anchor_for_table_cell("doc-1", table_id="t7", row_index=2, col_index=5)
    assert a.source_type == "table_cell"
    assert a.row_index == 2
    assert a.col_index == 5
    # A cell has no flat-text range — character offsets stay None.
    assert a.char_start is None
    assert a.char_end is None
    d = a.as_dict()
    assert "char_start" not in d
    assert "char_end" not in d
    assert "page" not in d  # page defaulted to None and is dropped
    assert d == {
        "doc_id": "doc-1",
        "source_type": "table_cell",
        "table_id": "t7",
        "row_index": 2,
        "col_index": 5,
    }


def test_table_cell_with_page_keeps_page() -> None:
    a = anchor_for_table_cell("doc-1", table_id="t7", row_index=0, col_index=0, page=4)
    assert a.page == 4
    assert a.as_dict()["page"] == 4


def test_caption_source_type() -> None:
    a = anchor_for_caption("doc-9", page=1, char_start=0, char_end=30)
    assert a.source_type == "figure_caption"
    assert a.as_dict() == {
        "doc_id": "doc-9",
        "source_type": "figure_caption",
        "page": 1,
        "char_start": 0,
        "char_end": 30,
    }


def test_as_dict_drops_none_fields() -> None:
    # Zero-index / zero-offset values are kept; only None is dropped.
    a = anchor_for_paragraph("d", page=0, char_start=0, char_end=0)
    d = a.as_dict()
    assert d == {
        "doc_id": "d",
        "source_type": "paragraph",
        "page": 0,
        "char_start": 0,
        "char_end": 0,
    }
    # None-valued table fields never leak in.
    assert all(v is not None for v in d.values())


def test_no_provenance_fields_ever() -> None:
    # §8.3 stub is location-only: no extractor / model / confidence keys exist.
    a = anchor_for_paragraph("d", page=1, char_start=1, char_end=2)
    d = a.as_dict()
    for forbidden in ("extractor", "model", "confidence"):
        assert forbidden not in d


def test_paragraph_backwards_span_raises() -> None:
    with pytest.raises(ValueError, match="precedes char_start"):
        anchor_for_paragraph("d", page=1, char_start=50, char_end=10)


def test_paragraph_negative_start_raises() -> None:
    with pytest.raises(ValueError, match="char_start must be >= 0"):
        anchor_for_paragraph("d", page=1, char_start=-1, char_end=10)


def test_caption_backwards_span_raises() -> None:
    with pytest.raises(ValueError, match="precedes char_start"):
        anchor_for_caption("d", page=1, char_start=5, char_end=4)


def test_table_cell_negative_row_raises() -> None:
    with pytest.raises(ValueError, match="row_index must be >= 0"):
        anchor_for_table_cell("d", table_id="t", row_index=-1, col_index=0)


def test_table_cell_negative_col_raises() -> None:
    with pytest.raises(ValueError, match="col_index must be >= 0"):
        anchor_for_table_cell("d", table_id="t", row_index=0, col_index=-3)


def test_bad_source_type_rejected() -> None:
    with pytest.raises(ValueError, match="source_type must be one of"):
        EvidenceAnchor(doc_id="d", source_type="footnote")


def test_empty_doc_id_rejected() -> None:
    with pytest.raises(ValueError, match="doc_id must be a non-empty string"):
        EvidenceAnchor(doc_id="", source_type="paragraph")


def test_anchor_is_frozen() -> None:
    a = anchor_for_paragraph("d", page=1, char_start=0, char_end=5)
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError is a dataclass detail
        a.char_start = 99  # type: ignore[misc]


def test_zero_width_span_allowed() -> None:
    # A half-open [7, 7) span is legal (empty but not backwards).
    a = anchor_for_paragraph("d", page=2, char_start=7, char_end=7)
    assert a.char_start == a.char_end == 7
