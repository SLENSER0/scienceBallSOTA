"""Ingest job status store (§5.6 job status, §14.10 /ingest/jobs)."""

from __future__ import annotations

import pytest

from kg_common.storage.jobs import Job, JobStore


@pytest.fixture
def store() -> JobStore:
    s = JobStore("sqlite:///:memory:")
    s.migrate()
    return s


def test_create_and_get(store: JobStore) -> None:
    """create_job seeds a queued job; get_job round-trips every field (§5.6)."""
    job = store.create_job("job:1", kind="ingest", total=10)
    assert isinstance(job, Job)
    assert job.job_id == "job:1"
    assert job.kind == "ingest"
    assert job.status == "queued"
    assert job.total == 10
    assert job.done == 0
    assert job.progress == 0.0
    assert job.error is None
    assert job.created_at and job.updated_at

    got = store.get_job("job:1")
    assert got == job
    assert store.get_job("missing") is None


def test_update_progress_recomputes_fraction(store: JobStore) -> None:
    """update_progress writes done and recomputes progress = done/total (§5.6)."""
    store.create_job("job:1", kind="ingest", total=8)
    updated = store.update_progress("job:1", done=2)
    assert updated is not None
    assert updated.done == 2
    assert updated.progress == pytest.approx(0.25)  # 2 / 8

    updated = store.update_progress("job:1", done=6)
    assert updated is not None
    assert updated.progress == pytest.approx(0.75)  # 6 / 8


def test_set_status_running_to_succeeded(store: JobStore) -> None:
    """A job walks queued → running → succeeded via set_status (§5.6)."""
    store.create_job("job:1", kind="ingest", total=4)
    running = store.set_status("job:1", "running")
    assert running is not None and running.status == "running"

    done = store.set_status("job:1", "succeeded")
    assert done is not None and done.status == "succeeded"
    assert done.error is None
    assert store.get_job("job:1").status == "succeeded"


def test_cancel_sets_cancelled(store: JobStore) -> None:
    """cancel transitions the job to the terminal cancelled status (§5.6)."""
    store.create_job("job:1", kind="reindex", total=100)
    cancelled = store.cancel("job:1")
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert store.get_job("job:1").status == "cancelled"


def test_list_filter_by_status_and_kind(store: JobStore) -> None:
    """list_jobs filters by status and/or kind (§14.10)."""
    store.create_job("a", kind="ingest", total=1)
    store.create_job("b", kind="ingest", total=1)
    store.create_job("c", kind="reindex", total=1)
    store.set_status("b", "running")
    store.set_status("c", "running")

    assert {j.job_id for j in store.list_jobs()} == {"a", "b", "c"}
    assert {j.job_id for j in store.list_jobs(status="running")} == {"b", "c"}
    assert {j.job_id for j in store.list_jobs(kind="ingest")} == {"a", "b"}
    assert {j.job_id for j in store.list_jobs(status="running", kind="ingest")} == {"b"}
    assert store.list_jobs(status="queued", kind="reindex") == []


def test_failed_carries_error(store: JobStore) -> None:
    """A failed job persists its error text for /ingest/jobs (§5.6)."""
    store.create_job("job:1", kind="ingest", total=3)
    failed = store.set_status("job:1", "failed", error="parser boom: bad PDF")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "parser boom: bad PDF"
    # round-trips and is exposed in the JSON dict for the API
    reread = store.get_job("job:1")
    assert reread.error == "parser boom: bad PDF"
    assert reread.as_dict()["error"] == "parser boom: bad PDF"


def test_progress_clamped_when_done_exceeds_total(store: JobStore) -> None:
    """An over-count (done > total) saturates progress at 1.0, never above (§5.6)."""
    store.create_job("job:1", kind="ingest", total=10)
    over = store.update_progress("job:1", done=15)  # 15 / 10 = 1.5 → clamp 1.0
    assert over is not None
    assert over.done == 15
    assert over.progress == 1.0


def test_progress_zero_total_and_status_override(store: JobStore) -> None:
    """total=0 avoids division-by-zero (progress 0.0); update_progress can set status."""
    store.create_job("job:1", kind="ingest", total=0)
    updated = store.update_progress("job:1", done=5, status="running")
    assert updated is not None
    assert updated.progress == 0.0  # no ZeroDivisionError
    assert updated.status == "running"
    # unknown ids and bad statuses are rejected cleanly
    assert store.update_progress("nope", done=1) is None
    assert store.set_status("nope", "running") is None
    with pytest.raises(ValueError):
        store.set_status("job:1", "bogus")
