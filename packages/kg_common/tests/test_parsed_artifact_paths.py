"""Hand-checkable tests for §5.5 parsed-artifact key builders."""

from __future__ import annotations

import pytest

from kg_common.storage.parsed_artifact_paths import DocumentArtifactPaths


def _paths() -> DocumentArtifactPaths:
    return DocumentArtifactPaths(doc_id="x", ext="pdf")


def test_raw_key_uses_ext() -> None:
    assert _paths().raw_key() == "documents/doc:x/original.pdf"


def test_docling_json_key() -> None:
    assert _paths().docling_json_key() == "documents/doc:x/docling.json"


def test_markdown_key() -> None:
    assert _paths().markdown_key().endswith("document.md")
    assert _paths().markdown_key() == "documents/doc:x/document.md"


def test_table_key_zero_pads_from_one() -> None:
    assert _paths().table_key(1) == "documents/doc:x/tables/table_001.json"


def test_image_key_zero_pads_width_three() -> None:
    assert _paths().image_key(12).endswith("images/img_012.png")
    assert _paths().image_key(12) == "documents/doc:x/images/img_012.png"


def test_page_key_zero_pads_from_one() -> None:
    assert _paths().page_key(1).endswith("pages/page_001.json")
    assert _paths().page_key(1) == "documents/doc:x/pages/page_001.json"


def test_chunks_key() -> None:
    assert _paths().chunks_key().endswith("chunks.jsonl")
    assert _paths().chunks_key() == "documents/doc:x/chunks.jsonl"


def test_manifest_key() -> None:
    assert _paths().manifest_key() == "documents/doc:x/manifest.json"


@pytest.mark.parametrize("n", [0, -1, -5])
def test_counter_rejects_below_one(n: int) -> None:
    with pytest.raises(ValueError):
        _paths().table_key(n)
    with pytest.raises(ValueError):
        _paths().image_key(n)
    with pytest.raises(ValueError):
        _paths().page_key(n)


def test_as_dict_contains_buckets() -> None:
    d = _paths().as_dict()
    assert d["raw_bucket"] == "kg-raw"
    assert d["parsed_bucket"] == "kg-parsed"
    assert d["doc_id"] == "x"
    assert d["ext"] == "pdf"


def test_custom_buckets_flow_into_as_dict() -> None:
    p = DocumentArtifactPaths(doc_id="y", ext="docx", raw_bucket="r", parsed_bucket="p")
    d = p.as_dict()
    assert d["raw_bucket"] == "r"
    assert d["parsed_bucket"] == "p"
    assert p.raw_key() == "documents/doc:y/original.docx"


def test_counter_boundary_999() -> None:
    assert _paths().table_key(999).endswith("table_999.json")
