"""Tests for §5.2.8 admin pipeline DAG view-model (:mod:`pipeline_dag`).

Тесты модели представления DAG конвейера для админ-панели (React Flow, §5.2.8).
"""

from __future__ import annotations

import json

from api_gateway.pipeline_dag import DX, PipelineDag, build_pipeline_dag
from api_gateway.pipeline_steps import PIPELINE_STEPS


def test_default_nodes_match_pipeline_steps() -> None:
    dag = build_pipeline_dag([])
    assert isinstance(dag, PipelineDag)
    assert len(dag.nodes) == len(PIPELINE_STEPS)


def test_default_layout_x_positions() -> None:
    dag = build_pipeline_dag([])
    assert dag.nodes[0]["position"]["x"] == 0
    assert dag.nodes[1]["position"]["x"] == 180
    assert dag.nodes[1]["position"]["x"] == DX


def test_edges_chain_consecutive_stages() -> None:
    dag = build_pipeline_dag([])
    assert len(dag.edges) == len(PIPELINE_STEPS) - 1
    assert dag.edges[0]["source"] == PIPELINE_STEPS[0]
    assert dag.edges[0]["target"] == PIPELINE_STEPS[1]


def test_all_nodes_default_to_pending() -> None:
    dag = build_pipeline_dag([])
    for node in dag.nodes:
        assert node["data"]["status"] == "pending"
        assert node["data"]["metrics"] == {}


def test_step_state_applies_status_and_metrics() -> None:
    dag = build_pipeline_dag([{"name": "parse", "status": "succeeded", "metrics": {"docs": 5}}])
    parse = next(n for n in dag.nodes if n["id"] == "parse")
    assert parse["data"]["status"] == "succeeded"
    assert parse["data"]["metrics"] == {"docs": 5}


def test_missing_stage_defaults_pending_empty_metrics() -> None:
    dag = build_pipeline_dag([{"name": "parse", "status": "succeeded", "metrics": {"docs": 5}}])
    # ``store`` was not supplied -> defaults.
    store = next(n for n in dag.nodes if n["id"] == "store")
    assert store["data"]["status"] == "pending"
    assert store["data"]["metrics"] == {}


def test_node_ids_are_stage_names_and_unique() -> None:
    dag = build_pipeline_dag([])
    ids = [n["id"] for n in dag.nodes]
    assert ids == list(PIPELINE_STEPS)
    assert len(ids) == len(set(ids))


def test_labels_match_stage_names() -> None:
    dag = build_pipeline_dag([])
    for node in dag.nodes:
        assert node["data"]["label"] == node["id"]


def test_as_dict_shape_and_first_position() -> None:
    dag = build_pipeline_dag([])
    payload = dag.as_dict()
    assert set(payload) == {"nodes", "edges"}
    assert payload["nodes"][0]["position"] == {"x": 0, "y": 0}


def test_as_dict_is_json_serialisable() -> None:
    dag = build_pipeline_dag([{"name": "parse", "status": "succeeded", "metrics": {"docs": 5}}])
    text = json.dumps(dag.as_dict())
    assert '"parse"' in text


def test_custom_dx_scales_layout() -> None:
    dag = build_pipeline_dag([], dx=100)
    assert dag.nodes[1]["position"]["x"] == 100
    assert dag.nodes[0]["position"]["x"] == 0


def test_missing_metrics_key_defaults_empty() -> None:
    dag = build_pipeline_dag([{"name": "chunk", "status": "running"}])
    chunk = next(n for n in dag.nodes if n["id"] == "chunk")
    assert chunk["data"]["status"] == "running"
    assert chunk["data"]["metrics"] == {}
