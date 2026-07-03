"""Tests for §10.5 OpenLineage-style RunEvent export (kg_common.lineage_export)."""

from __future__ import annotations

import json

import pytest

from kg_common.lineage_export import (
    DEFAULT_EVENT_TIME,
    lineage_event,
    to_json,
)
from kg_common.lineage_openlineage import DEFAULT_PRODUCER, SCHEMA_URL


def test_event_has_job_run_inputs_outputs() -> None:
    ev = lineage_event("ingest.chunk", "run:1", ["document:1"], ["chunks:1"])
    assert ev["job"] == {"namespace": "scienceball", "name": "ingest.chunk"}
    assert ev["run"] == {"runId": "run:1"}
    assert ev["inputs"] == [{"namespace": "scienceball", "name": "document:1"}]
    assert ev["outputs"] == [{"namespace": "scienceball", "name": "chunks:1"}]
    assert ev["producer"] == DEFAULT_PRODUCER
    assert ev["schemaURL"] == SCHEMA_URL
    assert ev["eventTime"] == DEFAULT_EVENT_TIME


def test_event_type_defaults_to_complete() -> None:
    ev = lineage_event("job", "run:1", [], [])
    assert ev["eventType"] == "COMPLETE"


def test_event_type_set_explicitly() -> None:
    ev = lineage_event("job", "run:1", [], [], event_type="START")
    assert ev["eventType"] == "START"


def test_invalid_event_type_rejected() -> None:
    with pytest.raises(ValueError, match="invalid eventType"):
        lineage_event("job", "run:1", [], [], event_type="DONE")


def test_inputs_outputs_rendered_as_dataset_facets() -> None:
    ev = lineage_event(
        "job",
        "run:1",
        ["a", {"namespace": "neo4j", "name": "kg"}],
        ["out"],
    )
    # each input/output is an OpenLineage dataset {namespace, name}
    assert ev["inputs"] == [
        {"namespace": "scienceball", "name": "a"},
        {"namespace": "neo4j", "name": "kg"},
    ]
    assert ev["outputs"] == [{"namespace": "scienceball", "name": "out"}]
    for ds in ev["inputs"] + ev["outputs"]:
        assert set(ds) == {"namespace", "name"}


def test_empty_io_yields_empty_lists() -> None:
    ev = lineage_event("job", "run:1", None, None)
    assert ev["inputs"] == []
    assert ev["outputs"] == []


def test_to_json_round_trip() -> None:
    ev = lineage_event("job", "run:1", ["a"], ["b"])
    restored = json.loads(to_json(ev))
    assert restored == ev


def test_to_json_deterministic_sorted_keys() -> None:
    ev = lineage_event("job", "run:1", ["a"], ["b"])
    first = to_json(ev)
    second = to_json(ev)
    assert first == second
    # sort_keys=True => 'eventTime' precedes 'eventType' precedes 'inputs'
    assert first.index('"eventTime"') < first.index('"eventType"') < first.index('"inputs"')


def test_lineage_event_deterministic_same_args() -> None:
    a = lineage_event("job", "run:1", ["x"], ["y"])
    b = lineage_event("job", "run:1", ["x"], ["y"])
    assert a == b
    assert to_json(a) == to_json(b)


def test_custom_namespace_and_event_time() -> None:
    ev = lineage_event(
        "job",
        "run:1",
        ["a"],
        [],
        namespace="lab",
        event_time="2026-07-03T10:00:00Z",
    )
    assert ev["job"]["namespace"] == "lab"
    assert ev["inputs"] == [{"namespace": "lab", "name": "a"}]
    assert ev["eventTime"] == "2026-07-03T10:00:00Z"
