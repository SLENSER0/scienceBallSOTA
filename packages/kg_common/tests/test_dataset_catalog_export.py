"""Dataset-catalog JSON export + summary (§9.2/§10.4)."""

from __future__ import annotations

import json

from kg_common.dataset_catalog_export import (
    CatalogSummary,
    catalog_from_json,
    catalog_summary,
    catalog_to_json,
)
from kg_common.storage.metadata_dtos import (
    DatasetMetadata,
    DocumentMetadata,
    SourceMetadata,
)

# Small fixed catalog — two owners (alice/bob), two docs, one dataset.
SOURCES = [
    SourceMetadata(source_id="s1", name="лаб-1", owner="alice", lab="materials", version=2),
    SourceMetadata(source_id="s2", name="лаб-2", owner="bob", lab="chem"),
    SourceMetadata(source_id="s3", name="лаб-3", owner="alice"),
]
DOCUMENTS = [
    DocumentMetadata(doc_id="d1", source_id="s1", title="медь", n_pages=3),
    DocumentMetadata(doc_id="d2", source_id="s2", title="железо"),
]
DATASETS = [
    DatasetMetadata(dataset_id="ds1", doc_id="d1", kind="table", row_count=42),
]


def test_json_round_trips_back_to_dtos() -> None:
    text = catalog_to_json(SOURCES, DOCUMENTS, DATASETS)
    sources, documents, datasets = catalog_from_json(text)
    # from_json(to_json(x)) == x, element-by-element, types preserved.
    assert sources == SOURCES
    assert documents == DOCUMENTS
    assert datasets == DATASETS
    assert sources[0].version == 2  # int stays int through the round-trip


def test_json_shape_and_keys() -> None:
    payload = json.loads(catalog_to_json(SOURCES, DOCUMENTS, DATASETS))
    assert set(payload) == {"sources", "documents", "datasets"}
    assert [s["source_id"] for s in payload["sources"]] == ["s1", "s2", "s3"]
    assert payload["sources"][0]["owner"] == "alice"
    assert payload["datasets"][0]["row_count"] == 42
    assert "медь" in payload["documents"][0]["title"]  # RU preserved, not escaped


def test_summary_counts() -> None:
    summary = catalog_summary(SOURCES, DOCUMENTS, DATASETS)
    assert isinstance(summary, CatalogSummary)
    assert summary.n_sources == 3
    assert summary.n_documents == 2
    assert summary.n_datasets == 1


def test_summary_by_owner() -> None:
    summary = catalog_summary(SOURCES, DOCUMENTS, DATASETS)
    # alice owns s1 + s3, bob owns s2; keys sorted for determinism.
    assert summary.by_owner == {"alice": 2, "bob": 1}
    assert list(summary.by_owner) == ["alice", "bob"]


def test_empty_catalog() -> None:
    text = catalog_to_json([], [], [])
    assert json.loads(text) == {"sources": [], "documents": [], "datasets": []}
    assert catalog_from_json(text) == ([], [], [])
    summary = catalog_summary([], [], [])
    assert summary.as_dict() == {
        "n_sources": 0,
        "n_documents": 0,
        "n_datasets": 0,
        "by_owner": {},
    }


def test_deterministic_output() -> None:
    a = catalog_to_json(SOURCES, DOCUMENTS, DATASETS)
    b = catalog_to_json(SOURCES, DOCUMENTS, DATASETS)
    assert a == b  # equal inputs -> byte-identical JSON (sort_keys)
    # Keys inside each object are sorted regardless of dataclass field order.
    first_source = json.loads(a)["sources"][0]
    assert list(first_source) == sorted(first_source)


def test_summary_as_dict() -> None:
    summary = catalog_summary(SOURCES, DOCUMENTS, DATASETS)
    assert summary.as_dict() == {
        "n_sources": 3,
        "n_documents": 2,
        "n_datasets": 1,
        "by_owner": {"alice": 2, "bob": 1},
    }
    # as_dict returns a plain, mutable copy — mutating it must not touch the DTO.
    d = summary.as_dict()
    d["by_owner"]["alice"] = 99
    assert summary.by_owner["alice"] == 2
