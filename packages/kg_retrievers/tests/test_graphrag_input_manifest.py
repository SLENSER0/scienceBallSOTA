"""§11.3 tests for graphrag_input_manifest — hand-checkable manifest build & lookup."""

from __future__ import annotations

from kg_retrievers.graphrag_input_manifest import (
    CorpusManifest,
    ManifestEntry,
    build_manifest,
    reverse_lookup,
)


def _doc(
    doc_id: str,
    file_hash: str,
    *,
    review_status: str = "approved",
    source_type: str = "pdf",
    source_path: str | None = None,
    access_policy: str = "public",
) -> dict:
    """Собрать входной doc-dict / assemble one input doc dict (§11.3)."""
    return {
        "doc_id": doc_id,
        "file_hash": file_hash,
        "review_status": review_status,
        "access_policy": access_policy,
        "source_type": source_type,
        "source_path": source_path or f"/corpus/{doc_id}.pdf",
    }


def test_duplicate_file_hash_collapsed_to_first() -> None:
    """Два дока с одним file_hash → 2 записи, дубль в filtered_out (§11.3)."""
    docs = [
        _doc("a1", "hashX"),
        _doc("a2", "hashX"),  # duplicate content of a1
        _doc("a3", "hashY"),
    ]
    manifest = build_manifest("build-1", docs)
    assert [e.doc_id for e in manifest.entries] == ["a1", "a3"]
    assert len(manifest.entries) == 2
    assert manifest.filtered_out == ["a2"]


def test_rejected_review_status_excluded() -> None:
    """review_status='rejected' → исключён и попадает в filtered_out (§11.3)."""
    docs = [
        _doc("ok1", "h1"),
        _doc("bad", "h2", review_status="rejected"),
        _doc("ok2", "h3"),
    ]
    manifest = build_manifest("build-2", docs)
    assert [e.doc_id for e in manifest.entries] == ["ok1", "ok2"]
    assert "bad" in manifest.filtered_out
    assert manifest.filtered_out == ["bad"]


def test_graphrag_document_id_is_doc_id_dot_txt() -> None:
    """graphrag_document_id для 'd7' == 'd7.txt' (§11.3)."""
    manifest = build_manifest("build-3", [_doc("d7", "hh")])
    assert manifest.entries[0].graphrag_document_id == "d7.txt"


def test_reverse_lookup_hit_and_miss() -> None:
    """reverse_lookup('d7.txt') == 'd7'; неизвестный → None (§11.3)."""
    manifest = build_manifest("build-4", [_doc("d7", "hh")])
    assert reverse_lookup(manifest, "d7.txt") == "d7"
    assert reverse_lookup(manifest, "nope.txt") is None


def test_surviving_order_follows_input() -> None:
    """Порядок выживших записей = порядок входа (§11.3)."""
    docs = [
        _doc("z", "h1"),
        _doc("m", "h2"),
        _doc("a", "h3"),
    ]
    manifest = build_manifest("build-5", docs)
    assert [e.doc_id for e in manifest.entries] == ["z", "m", "a"]


def test_as_dict_entries_length_and_build_id_roundtrip() -> None:
    """as_dict()['entries'] длина совпадает; build_id round-trips (§11.3)."""
    docs = [
        _doc("a1", "hashX"),
        _doc("a2", "hashX"),  # dup -> dropped
        _doc("a3", "hashY"),
        _doc("bad", "hashZ", review_status="rejected"),  # dropped
    ]
    manifest = build_manifest("build-XYZ", docs)
    d = manifest.as_dict()
    assert d["build_id"] == "build-XYZ"
    assert len(d["entries"]) == len(manifest.entries) == 2
    assert d["filtered_out"] == ["a2", "bad"]


def test_entry_as_dict_exact_shape() -> None:
    """ManifestEntry.as_dict() отдаёт все 5 полей точно (§11.3)."""
    entry = ManifestEntry(
        doc_id="d7",
        graphrag_document_id="d7.txt",
        source_path="/corpus/d7.pdf",
        file_hash="abc",
        source_type="pdf",
    )
    assert entry.as_dict() == {
        "doc_id": "d7",
        "graphrag_document_id": "d7.txt",
        "source_path": "/corpus/d7.pdf",
        "file_hash": "abc",
        "source_type": "pdf",
    }


def test_frozen_dataclasses_are_immutable() -> None:
    """ManifestEntry/CorpusManifest — frozen (§11.3)."""
    entry = ManifestEntry("d7", "d7.txt", "/p", "h", "pdf")
    manifest = CorpusManifest("b", [entry], [])
    for obj, field in ((entry, "doc_id"), (manifest, "build_id")):
        try:
            setattr(obj, field, "x")
        except AttributeError:
            continue
        raise AssertionError("frozen dataclass must reject attribute assignment")


def test_custom_drop_status_tuple() -> None:
    """Кастомный drop_status выбрасывает соответствующие статусы (§11.3)."""
    docs = [
        _doc("keep", "h1", review_status="approved"),
        _doc("gone", "h2", review_status="quarantined"),
    ]
    manifest = build_manifest("b", docs, drop_status=("quarantined",))
    assert [e.doc_id for e in manifest.entries] == ["keep"]
    assert manifest.filtered_out == ["gone"]
