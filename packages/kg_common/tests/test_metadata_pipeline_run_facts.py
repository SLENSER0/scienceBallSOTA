"""Tests for run-level pipeline facts — тесты фактов запуска (§10.5)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.metadata.pipeline_run_facts import (
    RunFacts,
    from_run,
    is_failed,
    rollup,
)


def test_from_run_uppercases_status() -> None:
    fact = from_run({"job_id": "j", "status": "success", "duration_s": 1.0})
    assert fact.status == "SUCCESS"


def test_from_run_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        from_run({"job_id": "j", "status": "weird"})


def test_from_run_rejects_negative_duration() -> None:
    with pytest.raises(ValueError):
        from_run({"job_id": "j", "status": "SUCCESS", "duration_s": -1.0})


def test_from_run_defaults_counters_to_zero() -> None:
    fact = from_run({"job_id": "j", "status": "RUNNING"})
    assert fact.duration_s == 0.0
    assert fact.n_documents == 0
    assert fact.n_chunks == 0
    assert fact.n_triples == 0
    assert fact.extractor == ""
    assert fact.model == ""


def test_from_run_populates_all_fields() -> None:
    fact = from_run(
        {
            "job_id": "run-42",
            "status": "success",
            "duration_s": 12.5,
            "n_documents": 3,
            "n_chunks": 30,
            "n_triples": 120,
            "extractor": "rebel",
            "model": "qwen2.5",
        }
    )
    assert fact.job_id == "run-42"
    assert fact.status == "SUCCESS"
    assert fact.duration_s == 12.5
    assert fact.n_documents == 3
    assert fact.n_chunks == 30
    assert fact.n_triples == 120
    assert fact.extractor == "rebel"
    assert fact.model == "qwen2.5"


def test_from_run_coerces_counter_types() -> None:
    fact = from_run({"job_id": "j", "status": "SUCCESS", "n_documents": "5", "duration_s": "2"})
    assert isinstance(fact.n_documents, int)
    assert fact.n_documents == 5
    assert isinstance(fact.duration_s, float)
    assert fact.duration_s == 2.0


def test_is_failed_true_for_failed() -> None:
    assert is_failed(from_run({"job_id": "j", "status": "FAILED"})) is True


def test_is_failed_false_for_success() -> None:
    assert is_failed(from_run({"job_id": "j", "status": "SUCCESS"})) is False


def test_rollup_empty_success_rate_zero() -> None:
    assert rollup([])["success_rate"] == 0.0


def test_rollup_empty_totals_zero() -> None:
    result = rollup([])
    assert result["n_runs"] == 0
    assert result["total_documents"] == 0
    assert result["total_chunks"] == 0
    assert result["total_triples"] == 0


def test_rollup_mixed_success_rate_half() -> None:
    facts = [
        from_run({"job_id": "a", "status": "SUCCESS"}),
        from_run({"job_id": "b", "status": "FAILED"}),
    ]
    assert rollup(facts)["success_rate"] == 0.5


def test_rollup_sums_triples() -> None:
    facts = [
        from_run({"job_id": "a", "status": "SUCCESS", "n_triples": 7}),
        from_run({"job_id": "b", "status": "FAILED", "n_triples": 5}),
    ]
    assert rollup(facts)["total_triples"] == 12


def test_rollup_sums_documents_and_chunks() -> None:
    facts = [
        from_run({"job_id": "a", "status": "SUCCESS", "n_documents": 2, "n_chunks": 20}),
        from_run({"job_id": "b", "status": "RUNNING", "n_documents": 3, "n_chunks": 30}),
    ]
    result = rollup(facts)
    assert result["total_documents"] == 5
    assert result["total_chunks"] == 50
    assert result["n_runs"] == 2


def test_rollup_running_not_counted_as_success() -> None:
    facts = [
        from_run({"job_id": "a", "status": "SUCCESS"}),
        from_run({"job_id": "b", "status": "RUNNING"}),
    ]
    assert rollup(facts)["success_rate"] == 0.5


def test_as_dict_n_documents_is_int() -> None:
    fact = RunFacts(job_id="j", status="SUCCESS", n_documents=4)
    assert isinstance(fact.as_dict()["n_documents"], int)


def test_as_dict_roundtrip_fields() -> None:
    fact = RunFacts(job_id="j", status="SUCCESS", n_triples=9, model="m")
    data = fact.as_dict()
    assert data["job_id"] == "j"
    assert data["status"] == "SUCCESS"
    assert data["n_triples"] == 9
    assert data["model"] == "m"


def test_runfacts_is_frozen() -> None:
    fact = RunFacts(job_id="j", status="SUCCESS")
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.status = "FAILED"  # type: ignore[misc]
