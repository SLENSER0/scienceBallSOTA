"""Tests for evidence_builder (§6.10 / §8.3) — Evidence node + Measurement links."""

from __future__ import annotations

import pytest

from kg_extractors.evidence_builder import (
    VALID_SOURCE_TYPES,
    Evidence,
    build_evidence,
    build_evidence_for_measurement,
    from_table_cell,
)


def test_paragraph_evidence_as_dict_has_section_8_3_fields() -> None:
    """A paragraph Evidence exposes every §8.3 field with the given values."""
    ev = build_evidence(
        doc_id="doc:al-cu-2024",
        page=7,
        source_type="paragraph",
        extractor="rule_extractor",
        model="rules",
        char_start=120,
        char_end=135,
    )
    assert ev.as_dict() == {
        "id": ev.id,
        "label": "Evidence",
        "doc_id": "doc:al-cu-2024",
        "page": 7,
        "source_type": "paragraph",
        "extractor": "rule_extractor",
        "model": "rules",
        "char_start": 120,
        "char_end": 135,
        "table_id": None,
        "row_index": None,
        "col_index": None,
        "review_status": "pending",
    }
    assert ev.id.startswith("ev:")


def test_table_cell_carries_table_id_row_col_and_from_table_edge() -> None:
    """table_cell Evidence carries coordinates and yields a FROM_TABLE edge."""
    ev = from_table_cell(
        doc_id="doc:matte-2023",
        page=3,
        table_id="tab:12",
        row_index=4,
        col_index=2,
        extractor="table_extractor",
        model="rules",
    )
    assert ev.source_type == "table_cell"
    assert ev.is_table_cell is True
    node = ev.as_dict()
    assert node["table_id"] == "tab:12"
    assert node["row_index"] == 4
    assert node["col_index"] == 2

    spec = build_evidence_for_measurement("meas:99", ev)
    edge = spec["from_source"]
    assert edge["type"] == "FROM_TABLE"
    assert edge["source"] == ev.id
    assert edge["target"] == "tab:12"
    assert edge["to_label"] == "Table"
    assert edge["row_index"] == 4
    assert edge["col_index"] == 2


def test_invalid_source_type_raises_value_error() -> None:
    """An unmodelled source_type is rejected with ValueError (§8.3)."""
    with pytest.raises(ValueError, match="invalid source_type"):
        build_evidence(
            doc_id="doc:1",
            page=1,
            source_type="footnote",
            extractor="x",
            model="m",
        )


def test_manual_source_type_is_not_accepted_by_builder() -> None:
    """``manual`` is a curation-only origin — not in VALID_SOURCE_TYPES (§8.3)."""
    assert "manual" not in VALID_SOURCE_TYPES
    with pytest.raises(ValueError, match="invalid source_type"):
        build_evidence(doc_id="d", page=1, source_type="manual", extractor="x", model="m")


def test_supported_by_edge_links_measurement_to_evidence() -> None:
    """The SUPPORTED_BY edge goes Measurement → Evidence (§8.3)."""
    ev = build_evidence(
        doc_id="doc:1",
        page=2,
        source_type="paragraph",
        extractor="rule_extractor",
        model="rules",
        char_start=10,
        char_end=20,
    )
    spec = build_evidence_for_measurement("meas:1", ev)
    sb = spec["supported_by"]
    assert sb == {
        "source": "meas:1",
        "target": ev.id,
        "type": "SUPPORTED_BY",
        "from_label": "Measurement",
        "to_label": "Evidence",
    }


def test_exactly_one_evidence_per_measurement() -> None:
    """Invariant: exactly one SUPPORTED_BY edge per measurement (§8.3)."""
    ev = build_evidence(doc_id="doc:1", page=1, source_type="paragraph", extractor="x", model="m")
    spec = build_evidence_for_measurement("meas:7", ev)
    supported = [e for e in spec["edges"] if e["type"] == "SUPPORTED_BY"]
    assert len(supported) == 1
    assert spec["edges"][0]["type"] == "SUPPORTED_BY"
    assert spec["edges"][1]["type"] == "FROM_CHUNK"
    assert len(spec["edges"]) == 2


def test_figure_caption_source_type_uses_from_chunk() -> None:
    """A figure_caption span is a valid origin and links via FROM_CHUNK (§8.3)."""
    ev = build_evidence(
        doc_id="doc:fig",
        page=5,
        source_type="figure_caption",
        extractor="caption_extractor",
        model="rules",
        char_start=0,
        char_end=42,
    )
    assert ev.source_type == "figure_caption"
    assert ev.is_table_cell is False
    edge = build_evidence_for_measurement("meas:2", ev)["from_source"]
    assert edge["type"] == "FROM_CHUNK"
    assert edge["target"] == "doc:fig"
    assert edge["to_label"] == "Chunk"
    assert edge["char_start"] == 0
    assert edge["char_end"] == 42


def test_metadata_source_type_uses_from_chunk() -> None:
    """A metadata span is a valid origin and links via FROM_CHUNK (§8.3)."""
    ev = build_evidence(
        doc_id="doc:meta",
        page=1,
        source_type="metadata",
        extractor="metadata_extractor",
        model="rules",
    )
    assert ev.source_type == "metadata"
    edge = build_evidence_for_measurement("meas:3", ev)["from_source"]
    assert edge["type"] == "FROM_CHUNK"
    assert edge["source"] == ev.id
    assert edge["target"] == "doc:meta"
    assert edge["page"] == 1


def test_missing_span_offsets_allowed() -> None:
    """Character offsets may be omitted (missing span allowed, §6.10)."""
    ev = build_evidence(doc_id="doc:1", page=1, source_type="metadata", extractor="x", model="m")
    assert ev.char_start is None
    assert ev.char_end is None
    assert ev.as_dict()["char_start"] is None
    assert ev.as_dict()["char_end"] is None


def test_review_status_defaults_to_pending() -> None:
    """review_status defaults to 'pending' when not supplied (§3.8)."""
    ev = build_evidence(doc_id="doc:1", page=1, source_type="paragraph", extractor="x", model="m")
    assert ev.review_status == "pending"
    assert ev.as_dict()["review_status"] == "pending"


def test_review_status_accepts_valid_and_rejects_invalid() -> None:
    """A supplied review_status must be a valid ReviewStatus (§3.8)."""
    ev = build_evidence(
        doc_id="doc:1",
        page=1,
        source_type="paragraph",
        extractor="x",
        model="m",
        review_status="accepted",
    )
    assert ev.review_status == "accepted"
    with pytest.raises(ValueError, match="invalid review_status"):
        build_evidence(
            doc_id="doc:1",
            page=1,
            source_type="paragraph",
            extractor="x",
            model="m",
            review_status="approved",
        )


def test_evidence_id_deterministic_and_location_sensitive() -> None:
    """Same location → same id (idempotent); different offsets → different id."""
    kw = {
        "doc_id": "doc:1",
        "page": 2,
        "source_type": "paragraph",
        "extractor": "x",
        "model": "m",
        "char_start": 5,
        "char_end": 9,
    }
    a = build_evidence(**kw)
    b = build_evidence(**kw)
    c = build_evidence(**{**kw, "char_start": 6})
    assert a.id == b.id
    assert a.id != c.id
    assert a.id.startswith("ev:")
    assert len(a.id) == len("ev:") + 16


def test_frozen_dataclass_is_immutable() -> None:
    """Evidence is a frozen dataclass (§ house style) — fields cannot be reassigned."""
    ev = build_evidence(doc_id="doc:1", page=1, source_type="paragraph", extractor="x", model="m")
    assert isinstance(ev, Evidence)
    with pytest.raises(AttributeError):
        ev.page = 2  # type: ignore[misc]
