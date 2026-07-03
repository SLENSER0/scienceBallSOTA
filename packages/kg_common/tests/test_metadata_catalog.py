"""Metadata/lineage catalog store (§10.3/§10.4/§10.5)."""

from __future__ import annotations

import pytest

from kg_common.storage.metadata_catalog import (
    Dataset,
    LineageEdge,
    MetadataCatalog,
)


@pytest.fixture
def cat() -> MetadataCatalog:
    c = MetadataCatalog("sqlite:///:memory:")
    c.migrate()
    return c


def _seed_chain(cat: MetadataCatalog) -> None:
    """Seed a §9.1 mini-pipeline lineage: source→document→chunks→triples→neo4j,
    with a qdrant index branching off chunks."""
    edges = [
        ("source:1", "", "source"),
        ("document:1", "source:1", "document"),
        ("chunks:1", "document:1", "chunks"),
        ("triples:1", "chunks:1", "triples"),
        ("neo4j:kg", "triples:1", "neo4j"),
        ("qdrant:col", "chunks:1", "qdrant"),
    ]
    for asset, upstream, kind in edges:
        cat.record_lineage(
            LineageEdge("run:1", asset, upstream, kind=kind, started_at="2026-07-03T10:00:00")
        )


def test_register_and_get_dataset(cat: MetadataCatalog) -> None:
    cat.register_dataset(
        Dataset(
            "ds:neo4j",
            name="KG граф",
            kind="neo4j",
            uri="bolt://neo4j:7687",
            n_records=1200,
            owner="lab:mmk",
        )
    )
    ds = cat.get_dataset("ds:neo4j")
    assert ds is not None
    assert ds.name == "KG граф" and ds.kind == "neo4j" and ds.n_records == 1200
    assert ds.owner == "lab:mmk"
    assert ds.as_dict()["uri"] == "bolt://neo4j:7687"
    assert cat.get_dataset("ds:missing") is None


def test_register_dataset_is_idempotent_upsert(cat: MetadataCatalog) -> None:
    cat.register_dataset(Dataset("ds:q", kind="qdrant", n_records=0, owner="a"))
    cat.register_dataset(Dataset("ds:q", kind="qdrant", n_records=512, owner="b"))
    assert len(cat.list_datasets()) == 1  # UPSERT, not a second row
    ds = cat.get_dataset("ds:q")
    assert ds is not None and ds.n_records == 512 and ds.owner == "b"


def test_list_datasets_and_filters(cat: MetadataCatalog) -> None:
    cat.register_dataset(Dataset("ds:2", kind="qdrant", owner="lab:x"))
    cat.register_dataset(Dataset("ds:1", kind="neo4j", owner="lab:x"))
    cat.register_dataset(Dataset("ds:3", kind="qdrant", owner="lab:y"))
    assert [d.dataset_id for d in cat.list_datasets()] == ["ds:1", "ds:2", "ds:3"]
    assert [d.dataset_id for d in cat.list_datasets(kind="qdrant")] == ["ds:2", "ds:3"]
    assert [d.dataset_id for d in cat.list_datasets(owner="lab:y")] == ["ds:3"]
    assert cat.list_datasets(kind="opensearch") == []


def test_lineage_upstreams(cat: MetadataCatalog) -> None:
    _seed_chain(cat)
    assert cat.upstreams_of("document:1") == ["source:1"]
    assert cat.upstreams_of("neo4j:kg") == ["triples:1"]
    # a root asset has an empty upstream, which is excluded
    assert cat.upstreams_of("source:1") == []


def test_lineage_downstreams(cat: MetadataCatalog) -> None:
    _seed_chain(cat)
    # chunks:1 feeds both the triples extraction and the qdrant index (sorted)
    assert cat.downstreams_of("chunks:1") == ["qdrant:col", "triples:1"]
    assert cat.downstreams_of("document:1") == ["chunks:1"]
    assert cat.downstreams_of("neo4j:kg") == []


def test_lineage_for_touches_asset(cat: MetadataCatalog) -> None:
    _seed_chain(cat)
    edges = cat.lineage_for("chunks:1")
    # one inbound edge (chunks:1 from document:1) + two outbound (as upstream of
    # triples:1 and qdrant:col) = 3 edges touching chunks:1
    assert len(edges) == 3
    assert sorted(e.asset for e in edges) == ["chunks:1", "qdrant:col", "triples:1"]
    inbound = next(e for e in edges if e.asset == "chunks:1")
    assert inbound.upstream == "document:1" and inbound.kind == "chunks"


def test_record_lineage_idempotent_and_filter(cat: MetadataCatalog) -> None:
    # re-emitting the same edge updates status/timestamp, does not duplicate
    cat.record_lineage(LineageEdge("run:2", "extract", "chunks", status="running"))
    cat.record_lineage(LineageEdge("run:2", "extract", "chunks", status="success"))
    rows = cat.list_lineage(run_id="run:2")
    assert len(rows) == 1 and rows[0].status == "success"

    # a failed run is filterable by status (§10.5 FAILED-run трассируемость)
    cat.record_lineage(LineageEdge("run:3", "gap_scan", "neo4j:kg", status="failed"))
    cat.record_lineage(LineageEdge("run:3", "eval", "neo4j:kg", status="success"))
    assert [r.asset for r in cat.list_lineage(status="failed")] == ["gap_scan"]
    assert [r.asset for r in cat.list_lineage(run_id="run:3", status="success")] == ["eval"]
