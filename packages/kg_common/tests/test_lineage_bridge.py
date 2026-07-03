"""Bridge MetadataCatalog lineage → OpenLineage (§10.5/§10.9)."""

from __future__ import annotations

from kg_common.storage.lineage_bridge import emit_catalog_lineage
from kg_common.storage.metadata_catalog import LineageEdge, MetadataCatalog


def _catalog() -> MetadataCatalog:
    c = MetadataCatalog("sqlite:///:memory:")
    c.migrate()
    c.record_lineage(LineageEdge(run_id="r1", asset="chunks", upstream="raw_doc", kind="chunks"))
    c.record_lineage(LineageEdge(run_id="r1", asset="graph", upstream="chunks", kind="neo4j"))
    return c


def test_emit_full_lineage_maps_to_openlineage() -> None:
    ev = emit_catalog_lineage(
        _catalog(), job_name="corpus_refresh", run_id="r1", event_time="2026-07-03T00:00:00Z"
    )
    assert ev["eventType"] in {"START", "COMPLETE", "RUNNING", "OTHER"}
    assert ev["run"]["runId"] == "r1"
    assert ev["job"]["name"] == "corpus_refresh"
    names = {d["name"] for d in ev["inputs"]} | {d["name"] for d in ev["outputs"]}
    assert {"raw_doc", "chunks", "graph"} <= names


def test_emit_for_single_asset() -> None:
    ev = emit_catalog_lineage(
        _catalog(), job_name="j", run_id="r1", event_time="2026-07-03T00:00:00Z", asset="graph"
    )
    outputs = {d["name"] for d in ev["outputs"]}
    inputs = {d["name"] for d in ev["inputs"]}
    assert "graph" in outputs and "chunks" in inputs
