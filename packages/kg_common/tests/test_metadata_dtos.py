"""Metadata DTOs + register helpers (§9.2/§10.4)."""

from __future__ import annotations

import pytest

from kg_common.storage.metadata_catalog import MetadataCatalog
from kg_common.storage.metadata_dtos import (
    DatasetMetadata,
    DocumentMetadata,
    SourceMetadata,
    get_dataset_meta,
    get_document,
    get_source,
    list_documents,
    list_sources,
    next_version,
    register_dataset_meta,
    register_document,
    register_source,
)


@pytest.fixture
def cat() -> MetadataCatalog:
    c = MetadataCatalog("sqlite:///:memory:")
    c.migrate()
    return c


# -- DTO round-trips ------------------------------------------------------
def test_source_metadata_roundtrips(cat: MetadataCatalog) -> None:
    meta = SourceMetadata(
        "src:mmk",
        name="ММК отчёты",
        owner="user:ivanov",
        lab="lab:mmk",
        access_policy="lab-restricted",
        version=3,
        ingestion_job_id="job:42",
        created_at="2026-07-03T10:00:00",
    )
    d = meta.as_dict()
    assert d["source_id"] == "src:mmk" and d["access_policy"] == "lab-restricted"
    assert d["version"] == 3 and d["lab"] == "lab:mmk"
    assert SourceMetadata.from_dict(d) == meta  # exact value round-trip


def test_document_metadata_roundtrips() -> None:
    meta = DocumentMetadata(
        "doc:1",
        source_id="src:mmk",
        title="Протокол испытаний",
        media_type="application/pdf",
        n_pages=14,
        checksum="sha256:abc",
    )
    d = meta.as_dict()
    assert d["doc_id"] == "doc:1" and d["n_pages"] == 14
    assert d["media_type"] == "application/pdf" and d["checksum"] == "sha256:abc"
    assert DocumentMetadata.from_dict(d) == meta


def test_dataset_metadata_roundtrips() -> None:
    meta = DatasetMetadata("ds:1", doc_id="doc:1", kind="table", row_count=256)
    d = meta.as_dict()
    assert d == {"dataset_id": "ds:1", "doc_id": "doc:1", "kind": "table", "row_count": 256}
    assert DatasetMetadata.from_dict(d) == meta


def test_required_fields_enforced() -> None:
    # dataclass: the id is positional-required, omitting it is a TypeError
    with pytest.raises(TypeError):
        SourceMetadata()  # type: ignore[call-arg]
    # from_dict: a missing primary key raises a clear KeyError
    with pytest.raises(KeyError):
        SourceMetadata.from_dict({"name": "no id"})
    with pytest.raises(KeyError):
        DocumentMetadata.from_dict({"title": "no id"})
    with pytest.raises(KeyError):
        DatasetMetadata.from_dict({"kind": "table"})


# -- persistence ----------------------------------------------------------
def test_register_source_then_read_back(cat: MetadataCatalog) -> None:
    register_source(
        cat,
        SourceMetadata("src:1", name="A", owner="u1", lab="lab:x", version=2),
    )
    got = get_source(cat, "src:1")
    assert got is not None
    assert got.name == "A" and got.owner == "u1" and got.lab == "lab:x"
    assert got.version == 2


def test_register_document_links_to_source(cat: MetadataCatalog) -> None:
    register_source(cat, SourceMetadata("src:1", name="Source"))
    register_document(
        cat,
        DocumentMetadata("doc:1", source_id="src:1", title="Doc", n_pages=3),
    )
    doc = get_document(cat, "doc:1")
    assert doc is not None and doc.source_id == "src:1" and doc.n_pages == 3
    # the link resolves: the referenced source is itself readable
    assert get_source(cat, doc.source_id) is not None
    assert [d.doc_id for d in list_documents(cat, source_id="src:1")] == ["doc:1"]


def test_reregister_updates_not_duplicates(cat: MetadataCatalog) -> None:
    register_source(cat, SourceMetadata("src:1", name="old", owner="u1"))
    register_source(cat, SourceMetadata("src:1", name="new", owner="u2"))
    assert len(list_sources(cat)) == 1  # UPSERT, not a second row
    got = get_source(cat, "src:1")
    assert got is not None and got.name == "new" and got.owner == "u2"


def test_access_policy_preserved_through_store(cat: MetadataCatalog) -> None:
    register_source(cat, SourceMetadata("src:1", access_policy="public"))
    assert get_source(cat, "src:1").access_policy == "public"  # type: ignore[union-attr]
    # a later re-register with a stricter policy is the value that persists
    register_source(cat, SourceMetadata("src:1", access_policy="lab-restricted"))
    assert get_source(cat, "src:1").access_policy == "lab-restricted"  # type: ignore[union-attr]


def test_version_bump_path(cat: MetadataCatalog) -> None:
    src = SourceMetadata("src:1", name="v1", version=1)
    register_source(cat, src)
    assert get_source(cat, "src:1").version == 1  # type: ignore[union-attr]
    bumped = next_version(src)
    assert bumped.version == 2 and bumped.source_id == "src:1"
    register_source(cat, bumped)
    assert len(list_sources(cat)) == 1  # still one row after the bump
    assert get_source(cat, "src:1").version == 2  # type: ignore[union-attr]


def test_register_dataset_links_to_document(cat: MetadataCatalog) -> None:
    register_document(cat, DocumentMetadata("doc:1", source_id="src:1"))
    register_dataset_meta(cat, DatasetMetadata("ds:1", doc_id="doc:1", row_count=42))
    ds = get_dataset_meta(cat, "ds:1")
    assert ds is not None and ds.doc_id == "doc:1" and ds.row_count == 42


def test_unknown_read_returns_none(cat: MetadataCatalog) -> None:
    assert get_source(cat, "src:missing") is None
    assert get_document(cat, "doc:missing") is None
    assert get_dataset_meta(cat, "ds:missing") is None
