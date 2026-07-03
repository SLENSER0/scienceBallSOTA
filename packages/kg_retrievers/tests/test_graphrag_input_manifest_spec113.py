"""§11.3 tests — GraphRAG input manifest (spec-113 variant).

RU: Хендл-чекаемые тесты: конкретные ожидаемые значения, без случайности.
EN: Hand-checkable tests asserting concrete expected values, no randomness.
"""

from __future__ import annotations

import json

from kg_retrievers.graphrag_input_manifest_spec113 import (
    InputManifest,
    ManifestEntry,
    build_manifest,
    manifest_lookup,
)


def _doc(doc_id: str, file_hash: str, review_status: str | None = None) -> dict:
    """Собрать входной doc-dict / assemble one input doc dict."""
    doc: dict = {
        "doc_id": doc_id,
        "file_hash": file_hash,
        "source_path": f"/corpus/{doc_id}.pdf",
        "source_type": "pdf",
    }
    if review_status is not None:
        doc["review_status"] = review_status
    return doc


def test_three_unique_docs_yield_three_entries() -> None:
    """(1) 3 уникальных документа → 3 записи, счётчики нулевые."""
    m = build_manifest(
        "build-1",
        [_doc("a", "h1"), _doc("b", "h2"), _doc("c", "h3")],
    )
    assert isinstance(m, InputManifest)
    assert len(m.entries) == 3
    assert m.skipped_rejected == 0
    assert m.skipped_duplicate == 0
    assert [e.doc_id for e in m.entries] == ["a", "b", "c"]


def test_rejected_doc_excluded_and_counted() -> None:
    """(2) review_status='rejected' исключается, skipped_rejected == 1."""
    m = build_manifest(
        "build-2",
        [_doc("a", "h1"), _doc("b", "h2", review_status="rejected"), _doc("c", "h3")],
    )
    assert len(m.entries) == 2
    assert m.skipped_rejected == 1
    assert m.skipped_duplicate == 0
    assert [e.doc_id for e in m.entries] == ["a", "c"]


def test_duplicate_file_hash_first_wins() -> None:
    """(3) два документа с одинаковым file_hash → одна запись, skipped_duplicate == 1."""
    m = build_manifest(
        "build-3",
        [_doc("a", "same"), _doc("b", "same")],
    )
    assert len(m.entries) == 1
    assert m.skipped_duplicate == 1
    assert m.skipped_rejected == 0
    # первое вхождение выигрывает / first occurrence wins
    assert m.entries[0].doc_id == "a"


def test_document_id_is_doc_id_dot_txt() -> None:
    """(4) document_id == f'{doc_id}.txt'."""
    m = build_manifest("build-4", [_doc("paper-42", "h1")])
    entry = m.entries[0]
    assert entry.document_id == "paper-42.txt"
    assert entry.document_id == f"{entry.doc_id}.txt"


def test_entries_sorted_ascending_by_doc_id() -> None:
    """(5) записи отсортированы по doc_id по возрастанию, даже если вход не отсортирован."""
    m = build_manifest(
        "build-5",
        [_doc("gamma", "h1"), _doc("alpha", "h2"), _doc("beta", "h3")],
    )
    assert [e.doc_id for e in m.entries] == ["alpha", "beta", "gamma"]


def test_manifest_lookup_hit_and_miss() -> None:
    """(6) manifest_lookup находит известный document_id и возвращает None иначе."""
    m = build_manifest("build-6", [_doc("a", "h1"), _doc("b", "h2")])
    hit = manifest_lookup(m, "a.txt")
    assert isinstance(hit, ManifestEntry)
    assert hit.doc_id == "a"
    assert hit.document_id == "a.txt"
    assert manifest_lookup(m, "missing.txt") is None


def test_as_dict_entries_is_json_roundtrippable_list_of_dicts() -> None:
    """(7) as_dict()['entries'] — список dict, round-trip через json.dumps."""
    m = build_manifest(
        "build-7",
        [_doc("a", "h1"), _doc("b", "h2", review_status="rejected"), _doc("c", "h1")],
    )
    d = m.as_dict()
    assert isinstance(d["entries"], list)
    assert all(isinstance(e, dict) for e in d["entries"])
    assert d["build_id"] == "build-7"
    assert d["skipped_rejected"] == 1
    assert d["skipped_duplicate"] == 1
    # ровно один выживший ('a'); 'c' — дубль h1, 'b' — rejected
    assert [e["doc_id"] for e in d["entries"]] == ["a"]
    round_tripped = json.loads(json.dumps(d))
    assert round_tripped == d
    assert round_tripped["entries"][0]["document_id"] == "a.txt"
