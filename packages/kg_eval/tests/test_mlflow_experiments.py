"""Named MLflow experiment specs + convenience wrappers (§18.4).

All tests run fully offline через :class:`InMemoryRecorder` — без mlflow-сервера.
"""

from __future__ import annotations

import pytest

from kg_common.mlflow_utils import EXPERIMENTS, ExperimentRun, InMemoryRecorder
from kg_eval.mlflow_experiments import (
    ALL_SPECS,
    ANSWER_EXPERIMENT,
    ANSWER_SPEC,
    EXTRACTION_EXPERIMENT,
    EXTRACTION_SPEC,
    RETRIEVAL_EXPERIMENT,
    RETRIEVAL_SPEC,
    ExperimentSpec,
    log_answer_run,
    log_extraction_run,
    log_retrieval_run,
    spec_for,
)


def test_three_specs_present_with_the_right_names() -> None:
    # Имя-константы совпадают с mlflow_utils.EXPERIMENTS (в том же порядке).
    assert (EXTRACTION_EXPERIMENT, RETRIEVAL_EXPERIMENT, ANSWER_EXPERIMENT) == EXPERIMENTS
    assert EXPERIMENTS == ("extraction", "retrieval", "answer")
    assert EXTRACTION_SPEC.name == "extraction"
    assert RETRIEVAL_SPEC.name == "retrieval"
    assert ANSWER_SPEC.name == "answer"


def test_each_spec_lists_its_params_and_metrics() -> None:
    for spec in ALL_SPECS:
        assert isinstance(spec, ExperimentSpec)
        assert isinstance(spec.tracked_params, tuple) and spec.tracked_params
        assert isinstance(spec.tracked_metrics, tuple) and spec.tracked_metrics
    # Каждая поверхность несёт свои характерные поля.
    assert "recall_at_k" in RETRIEVAL_SPEC.tracked_metrics
    assert "retriever" in RETRIEVAL_SPEC.tracked_params
    assert "entity_f1" in EXTRACTION_SPEC.tracked_metrics
    assert "faithfulness" in ANSWER_SPEC.tracked_metrics


def test_all_specs_covers_the_three_experiments() -> None:
    assert len(ALL_SPECS) == 3
    assert {s.name for s in ALL_SPECS} == set(EXPERIMENTS)
    assert ALL_SPECS == (EXTRACTION_SPEC, RETRIEVAL_SPEC, ANSWER_SPEC)


def test_log_retrieval_run_records_recall_at_k_under_retrieval() -> None:
    rec = InMemoryRecorder()
    run = log_retrieval_run(
        {"recall_at_k": 0.8, "mrr": 0.5},
        params={"retriever": "hybrid", "k": 10},
        recorder=rec,
    )
    # Метрика попала в recorder под экспериментом retrieval.
    assert rec.metrics["recall_at_k"] == 0.8
    assert rec.params == {"retriever": "hybrid", "k": 10}
    assert isinstance(run, ExperimentRun)
    assert run.experiment == RETRIEVAL_EXPERIMENT
    assert run.metrics["recall_at_k"] == 0.8


def test_log_extraction_run_records_metrics_under_extraction() -> None:
    rec = InMemoryRecorder()
    run = log_extraction_run(
        {"entity_f1": 0.72, "latency_ms": 130},
        params={"model": "qwen-2.5-7b", "temperature": 0.0},
        recorder=rec,
    )
    assert run.experiment == EXTRACTION_EXPERIMENT
    assert rec.metrics == {"entity_f1": 0.72, "latency_ms": 130.0}
    assert rec.params == {"model": "qwen-2.5-7b", "temperature": 0.0}


def test_log_answer_run_records_metrics_under_answer() -> None:
    rec = InMemoryRecorder()
    run = log_answer_run(
        {"faithfulness": 0.9, "answer_relevance": 0.85},
        params={"model": "qwen-2.5-7b", "top_k": 5},
        recorder=rec,
    )
    assert run.experiment == ANSWER_EXPERIMENT
    assert rec.metrics["faithfulness"] == 0.9
    assert rec.metrics["answer_relevance"] == 0.85


def test_unknown_metric_is_tolerated_not_rejected() -> None:
    # Метрика вне tracked_metrics логируется как есть, без ошибки.
    rec = InMemoryRecorder()
    assert "made_up_metric" not in RETRIEVAL_SPEC.tracked_metrics
    run = log_retrieval_run({"made_up_metric": 1.5}, recorder=rec)
    assert rec.metrics["made_up_metric"] == 1.5
    assert run.metrics["made_up_metric"] == 1.5


def test_spec_for_lookup_and_unknown_rejected() -> None:
    assert spec_for(RETRIEVAL_EXPERIMENT) is RETRIEVAL_SPEC
    assert spec_for("extraction") is EXTRACTION_SPEC
    with pytest.raises(ValueError, match="unknown experiment"):
        spec_for("training")


def test_experiment_spec_as_dict() -> None:
    assert RETRIEVAL_SPEC.as_dict() == {
        "name": "retrieval",
        "tracked_params": ["retriever", "embedding_model", "k", "hybrid_weight", "rerank"],
        "tracked_metrics": ["recall_at_k", "precision_at_k", "mrr", "ndcg_at_k", "hit_at_k"],
    }


def test_wrappers_fall_back_to_in_memory_recorder_offline() -> None:
    # Без переданного recorder трекинг всё равно работает офлайн.
    run = log_extraction_run({"entity_f1": 0.5}, params={"model": "m"})
    assert isinstance(run, ExperimentRun)
    assert run.experiment == EXTRACTION_EXPERIMENT
    assert run.metrics["entity_f1"] == 0.5
    assert run.params == {"model": "m"}
