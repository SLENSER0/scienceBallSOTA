"""Tests for the canonical §9.1 pipeline-stage DAG — тесты графа стадий.

Hand-checkable assertions over :mod:`kg_common.pipeline_stages`: the declared
dependency edges, the topological order, transitive downstream-of-failure, and
the per-job step view.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_common.pipeline_stages import (
    PipelineStage,
    downstream_of_failure,
    job_step_view,
    pipeline_steps,
    topo_steps,
)

_EXPECTED_KEYS = {
    "register_source",
    "docling_parse",
    "store_parsed",
    "chunk",
    "extract",
    "units_normalization",
    "entity_resolution",
    "schema_validation",
    "graph_upsert",
    "qdrant_indexing",
    "opensearch_indexing",
    "gap_scan",
    "retrieval_eval",
}


def _by_key() -> dict[str, PipelineStage]:
    return {s.key: s for s in pipeline_steps()}


def test_stage_count_and_keys() -> None:
    steps = pipeline_steps()
    assert len(steps) >= 12
    assert {s.key for s in steps} == _EXPECTED_KEYS


def test_as_dict_shape() -> None:
    stage = _by_key()["graph_upsert"]
    assert stage.as_dict() == {
        "key": "graph_upsert",
        "deps": ["schema_validation"],
        "description": stage.description,
    }


def test_stage_is_frozen() -> None:
    stage = pipeline_steps()[0]
    with pytest.raises(FrozenInstanceError):
        stage.key = "mutated"  # type: ignore[misc]


def test_register_before_docling_in_topo() -> None:
    order = topo_steps()
    assert order.index("register_source") < order.index("docling_parse")


def test_graph_upsert_depends_on_schema_validation() -> None:
    assert "schema_validation" in _by_key()["graph_upsert"].deps


def test_both_index_stages_depend_on_schema_validation() -> None:
    stages = _by_key()
    assert "schema_validation" in stages["qdrant_indexing"].deps
    assert "schema_validation" in stages["opensearch_indexing"].deps


def test_retrieval_eval_deps_are_exactly_the_two_index_stages() -> None:
    deps = set(_by_key()["retrieval_eval"].deps)
    assert deps == {"qdrant_indexing", "opensearch_indexing"}


def test_topo_places_every_dep_before_its_stage() -> None:
    order = topo_steps()
    stages = _by_key()
    assert set(order) == _EXPECTED_KEYS
    assert len(order) == len(set(order))  # no duplicates
    for stage in stages.values():
        for dep in stage.deps:
            assert order.index(dep) < order.index(stage.key), (stage.key, dep)


def test_topo_is_deterministic() -> None:
    assert topo_steps() == topo_steps()


def test_downstream_of_graph_upsert_includes_gap_scan() -> None:
    down = downstream_of_failure("graph_upsert")
    assert "gap_scan" in down
    assert "graph_upsert" not in down  # never includes itself
    # Everything below graph_upsert must be skipped.
    assert set(down) == {
        "qdrant_indexing",
        "opensearch_indexing",
        "gap_scan",
        "retrieval_eval",
    }


def test_downstream_of_chunk_includes_retrieval_eval() -> None:
    down = downstream_of_failure("chunk")
    assert "retrieval_eval" in down
    # A chunk failure poisons everything after it, but not the two stages
    # that precede it.
    assert "register_source" not in down
    assert "docling_parse" not in down
    assert "store_parsed" not in down


def test_downstream_is_topologically_ordered() -> None:
    order = topo_steps()
    down = downstream_of_failure("schema_validation")
    positions = [order.index(k) for k in down]
    assert positions == sorted(positions)


def test_downstream_of_leaf_is_empty() -> None:
    assert downstream_of_failure("retrieval_eval") == []


def test_downstream_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        downstream_of_failure("nope")


def test_job_step_view_labels() -> None:
    view = job_step_view("schema_validation")
    order = topo_steps()
    by_key = {row["key"]: row["status"] for row in view}
    assert [row["key"] for row in view] == order  # topo order preserved
    assert by_key["schema_validation"] == "current"
    assert by_key["register_source"] == "done"
    assert by_key["graph_upsert"] == "pending"
    statuses = {row["status"] for row in view}
    assert statuses <= {"done", "current", "pending"}
    assert sum(1 for r in view if r["status"] == "current") == 1


def test_job_step_view_first_stage_has_no_done() -> None:
    view = job_step_view("register_source")
    assert view[0]["status"] == "current"
    assert all(r["status"] != "done" for r in view)


def test_job_step_view_last_stage_all_done_before() -> None:
    view = job_step_view("retrieval_eval")
    assert view[-1]["status"] == "current"
    assert all(r["status"] == "done" for r in view[:-1])


def test_job_step_view_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        job_step_view("nope")
