"""Tests for sensor RunRequest + run_key dedup — тесты заявок (§9.6)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_common.run_request import RunRequest, build_run_requests, dedup_keys


def test_empty_run_key_raises() -> None:
    """Empty run_key is rejected — пустой run_key недопустим."""
    with pytest.raises(ValueError, match="run_key"):
        RunRequest(run_key="", job_name="full_ingestion_job")


def test_empty_job_name_raises() -> None:
    """Empty job_name is rejected — пустой job_name недопустим."""
    with pytest.raises(ValueError, match="job_name"):
        RunRequest(run_key="doc:a", job_name="")


def test_build_two_requests_partition_key_is_doc_id() -> None:
    """Two new keys → two requests, partition_key == doc id — по заявке на ключ."""
    reqs = build_run_requests("full_ingestion_job", ["doc:a", "doc:b"])
    assert len(reqs) == 2
    assert [r.run_key for r in reqs] == ["doc:a", "doc:b"]
    assert [r.partition_key for r in reqs] == ["doc:a", "doc:b"]
    assert all(r.job_name == "full_ingestion_job" for r in reqs)


def test_duplicate_input_key_emitted_once() -> None:
    """Repeated 'doc:a' in input yields one request — дедуп повторов."""
    reqs = build_run_requests("full_ingestion_job", ["doc:a", "doc:a", "doc:b"])
    assert [r.run_key for r in reqs] == ["doc:a", "doc:b"]


def test_already_requested_key_skipped() -> None:
    """A key in already_requested is skipped — уже запущенный ключ пропущен."""
    reqs = build_run_requests(
        "full_ingestion_job",
        ["doc:a", "doc:b"],
        already_requested={"doc:a"},
    )
    assert [r.run_key for r in reqs] == ["doc:b"]


def test_tag_fn_result_attached() -> None:
    """tag_fn output is attached to .tags — теги из tag_fn."""
    reqs = build_run_requests(
        "full_ingestion_job",
        ["doc:a"],
        tag_fn=lambda key: {"doc": key, "kind": "ingest"},
    )
    assert dict(reqs[0].tags) == {"doc": "doc:a", "kind": "ingest"}


def test_no_tag_fn_gives_empty_tags() -> None:
    """No tag_fn → empty tags mapping — без tag_fn пустые теги."""
    reqs = build_run_requests("full_ingestion_job", ["doc:a"])
    assert dict(reqs[0].tags) == {}


def test_dedup_keys_unique_in_order() -> None:
    """dedup_keys returns unique run_keys in order — уникальные ключи по порядку."""
    reqs = (
        RunRequest(run_key="doc:a", job_name="j"),
        RunRequest(run_key="doc:b", job_name="j"),
        RunRequest(run_key="doc:a", job_name="j"),
        RunRequest(run_key="doc:c", job_name="j"),
    )
    assert dedup_keys(reqs) == ("doc:a", "doc:b", "doc:c")


def test_as_dict_run_key() -> None:
    """as_dict exposes run_key — сериализация ключа."""
    req = RunRequest(run_key="doc:a", job_name="full_ingestion_job")
    assert req.as_dict()["run_key"] == "doc:a"


def test_as_dict_full_shape() -> None:
    """as_dict carries all fields — полная сериализация."""
    req = RunRequest(
        run_key="doc:a",
        job_name="full_ingestion_job",
        partition_key="doc:a",
        tags={"k": "v"},
    )
    assert req.as_dict() == {
        "run_key": "doc:a",
        "job_name": "full_ingestion_job",
        "partition_key": "doc:a",
        "tags": {"k": "v"},
    }


def test_requests_preserve_input_order() -> None:
    """Requests keep input order — сохранение порядка входа."""
    keys = ["doc:c", "doc:a", "doc:b"]
    reqs = build_run_requests("full_ingestion_job", keys)
    assert [r.run_key for r in reqs] == keys


def test_run_request_is_frozen() -> None:
    """RunRequest is immutable — заявка неизменяема."""
    req = RunRequest(run_key="doc:a", job_name="j")
    with pytest.raises(FrozenInstanceError):
        req.run_key = "doc:b"  # type: ignore[misc]
