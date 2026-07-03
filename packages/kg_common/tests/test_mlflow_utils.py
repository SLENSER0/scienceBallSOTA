"""Optional MLflow experiment tracking (§18.4) — offline in-memory recorder."""

from __future__ import annotations

import pytest

from kg_common.mlflow_utils import (
    EXPERIMENTS,
    ExperimentRun,
    InMemoryRecorder,
    Recorder,
    RunHandle,
    compute_run_id,
    end,
    log_metrics,
    log_params,
    set_tags,
    start_run,
)


def test_experiments_are_the_three_tracked_surfaces() -> None:
    assert EXPERIMENTS == ("extraction", "retrieval", "answer")


def test_start_run_on_each_experiment_yields_handle() -> None:
    for name in EXPERIMENTS:
        handle = start_run(name, recorder=InMemoryRecorder())
        assert isinstance(handle, RunHandle)
        assert handle.experiment == name
        # run_id детерминирован для (experiment, "", "").
        assert handle.run_id == compute_run_id(name, "", "")


def test_start_run_falls_back_to_in_memory_recorder_offline() -> None:
    # Без mlflow и без tracking uri трекинг всё равно работает.
    handle = start_run("retrieval")
    assert isinstance(handle.recorder, InMemoryRecorder)
    assert isinstance(handle.recorder, Recorder)


def test_log_params_captured_in_recorder() -> None:
    rec = InMemoryRecorder()
    handle = start_run("extraction", recorder=rec)
    handle.log_params({"model": "qwen-2.5-7b", "temperature": 0.0})
    assert rec.params == {"model": "qwen-2.5-7b", "temperature": 0.0}


def test_log_metrics_captured_in_recorder() -> None:
    rec = InMemoryRecorder()
    handle = start_run("retrieval", recorder=rec)
    handle.log_metrics({"recall": 0.8, "latency_ms": 42})
    # Метрики нормализуются к float.
    assert rec.metrics == {"recall": 0.8, "latency_ms": 42.0}


def test_set_tags_captured_in_recorder() -> None:
    rec = InMemoryRecorder()
    handle = start_run("answer", recorder=rec)
    handle.set_tags({"env": "test", "n_docs": 3})
    assert rec.tags == {"env": "test", "n_docs": "3"}


def test_git_sha_and_dataset_version_on_run() -> None:
    handle = start_run(
        "extraction",
        recorder=InMemoryRecorder(),
        git_sha="abc123",
        dataset_version="v1",
    )
    run = handle.run
    assert run.git_sha == "abc123"
    assert run.dataset_version == "v1"
    assert run.run_id == "ede5783c85165652"


def test_run_id_is_deterministic() -> None:
    # Same inputs → same id; different inputs → different id.
    assert compute_run_id("extraction", "abc123", "v1") == compute_run_id(
        "extraction", "abc123", "v1"
    )
    assert compute_run_id("extraction", "abc123", "v1") == "ede5783c85165652"
    assert compute_run_id("retrieval", "abc123", "v1") == "3baadb87f8eefb71"
    assert compute_run_id("answer", "deadbeef", "2026-07-03") == "e4ccfe54fb6504e6"
    assert compute_run_id("extraction", "abc123", "v1") != compute_run_id(
        "retrieval", "abc123", "v1"
    )


def test_end_finalizes_run_and_recorder() -> None:
    rec = InMemoryRecorder()
    handle = start_run("extraction", recorder=rec)
    handle.log_params({"k": 1})
    snapshot = handle.end()
    assert isinstance(snapshot, ExperimentRun)
    assert handle.ended is True
    assert rec.ended is True
    # end() идемпотентен.
    assert handle.end().run_id == snapshot.run_id
    # После финализации логирование запрещено.
    with pytest.raises(RuntimeError, match="already ended"):
        handle.log_params({"late": 2})


def test_as_dict_round_trips_all_fields() -> None:
    handle = start_run(
        "answer",
        recorder=InMemoryRecorder(),
        git_sha="deadbeef",
        dataset_version="2026-07-03",
    )
    handle.log_params({"prompt": "p1"})
    handle.log_metrics({"f1": 0.9})
    handle.set_tags({"reviewer": "alice"})
    assert handle.run.as_dict() == {
        "experiment": "answer",
        "run_id": "e4ccfe54fb6504e6",
        "params": {"prompt": "p1"},
        "metrics": {"f1": 0.9},
        "tags": {"reviewer": "alice"},
        "git_sha": "deadbeef",
        "dataset_version": "2026-07-03",
    }


def test_unknown_experiment_rejected() -> None:
    with pytest.raises(ValueError, match="unknown experiment"):
        start_run("training", recorder=InMemoryRecorder())


def test_module_level_helpers_delegate_to_handle() -> None:
    rec = InMemoryRecorder()
    handle = start_run("retrieval", recorder=rec)
    log_params(handle, {"a": 1})
    log_metrics(handle, {"m": 2.0})
    set_tags(handle, {"t": "x"})
    snapshot = end(handle)
    assert rec.params == {"a": 1}
    assert rec.metrics == {"m": 2.0}
    assert rec.tags == {"t": "x"}
    assert snapshot.as_dict()["params"] == {"a": 1}
    assert handle.ended is True
