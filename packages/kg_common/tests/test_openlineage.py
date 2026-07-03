"""OpenLineage-format lineage events (§10.9)."""

from __future__ import annotations

import pytest

from kg_common.lineage_openlineage import (
    DEFAULT_PRODUCER,
    SCHEMA_URL,
    emit_run,
    from_lineage_edges,
    to_openlineage_event,
)
from kg_common.storage.metadata_catalog import LineageEdge

_T = "2026-07-03T10:00:00Z"


def test_event_has_all_required_openlineage_fields() -> None:
    ev = to_openlineage_event(
        "run:1",
        "ingest.chunk",
        "COMPLETE",
        ["document:1"],
        ["chunks:1"],
        event_time=_T,
    )
    assert ev["eventType"] == "COMPLETE"
    assert ev["eventTime"] == _T
    assert ev["run"] == {"runId": "run:1"}
    assert ev["job"] == {"namespace": "scienceball", "name": "ingest.chunk"}
    assert ev["inputs"] == [{"namespace": "scienceball", "name": "document:1"}]
    assert ev["outputs"] == [{"namespace": "scienceball", "name": "chunks:1"}]
    assert ev["producer"] == DEFAULT_PRODUCER
    assert ev["schemaURL"] == SCHEMA_URL


def test_invalid_event_type_rejected() -> None:
    with pytest.raises(ValueError, match="invalid eventType"):
        to_openlineage_event("run:1", "job", "DONE", [], [], event_time=_T)


def test_mapping_dataset_keeps_custom_namespace() -> None:
    ev = to_openlineage_event(
        "run:1",
        "job",
        "COMPLETE",
        [{"namespace": "neo4j", "name": "kg"}],
        None,
        event_time=_T,
    )
    assert ev["inputs"] == [{"namespace": "neo4j", "name": "kg"}]
    assert ev["outputs"] == []


def test_emit_run_returns_start_then_complete_same_run_id() -> None:
    events = emit_run("job", ["a"], ["b"], "run:xyz", _T)
    assert [e["eventType"] for e in events] == ["START", "COMPLETE"]
    assert events[0]["run"]["runId"] == events[1]["run"]["runId"] == "run:xyz"
    assert events[0]["inputs"] == [{"namespace": "scienceball", "name": "a"}]
    assert events[1]["outputs"] == [{"namespace": "scienceball", "name": "b"}]


def test_emit_run_terminal_status_fail() -> None:
    events = emit_run("job", [], [], "run:1", _T, status="FAIL")
    assert [e["eventType"] for e in events] == ["START", "FAIL"]


def test_emit_run_invalid_terminal_status_rejected() -> None:
    with pytest.raises(ValueError, match="terminal status"):
        emit_run("job", [], [], "run:1", _T, status="START")


def test_from_lineage_edges_maps_upstream_to_inputs_asset_to_outputs() -> None:
    edges = [
        {"asset": "source:1", "upstream": ""},
        {"asset": "document:1", "upstream": "source:1"},
        {"asset": "chunks:1", "upstream": "document:1"},
    ]
    ev = from_lineage_edges(edges, run_id="run:1", job_name="pipeline", event_time=_T)
    assert ev["eventType"] == "COMPLETE"
    # empty upstream (root asset) excluded from inputs; order preserved
    assert [d["name"] for d in ev["inputs"]] == ["source:1", "document:1"]
    assert [d["name"] for d in ev["outputs"]] == ["source:1", "document:1", "chunks:1"]


def test_from_lineage_edges_accepts_dataclass_edges_and_dedups() -> None:
    edges = [
        LineageEdge("run:1", "triples:1", "chunks:1", kind="triples"),
        LineageEdge("run:1", "neo4j:kg", "triples:1", kind="neo4j"),
        LineageEdge("run:1", "qdrant:col", "chunks:1", kind="qdrant"),
    ]
    ev = from_lineage_edges(edges, run_id="run:1", job_name="load", event_time=_T)
    # chunks:1 appears twice as upstream -> deduplicated to a single input
    assert [d["name"] for d in ev["inputs"]] == ["chunks:1", "triples:1"]
    assert [d["name"] for d in ev["outputs"]] == ["triples:1", "neo4j:kg", "qdrant:col"]


def test_missing_run_id_raises() -> None:
    with pytest.raises(ValueError, match="run_id"):
        to_openlineage_event("", "job", "COMPLETE", [], [], event_time=_T)


def test_missing_job_name_and_event_time_raise() -> None:
    with pytest.raises(ValueError, match="job_name"):
        to_openlineage_event("run:1", "", "COMPLETE", [], [], event_time=_T)
    with pytest.raises(ValueError, match="event_time"):
        to_openlineage_event("run:1", "job", "COMPLETE", [], [], event_time="")
