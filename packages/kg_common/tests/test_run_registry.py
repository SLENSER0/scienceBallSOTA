"""Pipeline-run registry (§9.7): record/finish/recent over an explicit timeline."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from kg_common.storage.run_registry import PipelineRun, RunRegistry

# Explicit, deterministic ISO-8601 timestamps (the store never invents its own).
T10 = "2026-07-03T10:00:00+00:00"
T11 = "2026-07-03T11:00:00+00:00"
T12 = "2026-07-03T12:00:00+00:00"
T09 = "2026-07-03T09:00:00+00:00"


@pytest.fixture
def reg() -> RunRegistry:
    r = RunRegistry("sqlite:///:memory:")
    r.migrate()
    return r


def test_record_and_get(reg: RunRegistry) -> None:
    """record_run seeds a running run; get_run round-trips every field (§9.7)."""
    run = reg.record_run("run:1", kind="ingest", started_at=T10)
    assert isinstance(run, PipelineRun)
    assert run.run_id == "run:1"
    assert run.kind == "ingest"
    assert run.status == "running"
    assert run.started_at == T10
    assert run.finished_at is None
    assert run.stats == {}

    got = reg.get_run("run:1")
    assert got == run


def test_finish_sets_status_and_finished_at(reg: RunRegistry) -> None:
    """finish_run stamps finished_at and flips status to succeeded (§9.7)."""
    reg.record_run("run:1", kind="ingest", started_at=T10)
    finished = reg.finish_run("run:1", finished_at=T11)
    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.finished_at == T11
    # persisted, not just returned
    reread = reg.get_run("run:1")
    assert reread.status == "succeeded"
    assert reread.finished_at == T11
    assert reread.stats == {}  # untouched when no stats passed to finish


def test_finish_failed_records_status_and_final_stats(reg: RunRegistry) -> None:
    """finish_run can record a failed run plus final stats in one write (§9.7)."""
    reg.record_run("run:1", kind="ingest", started_at=T10, stats={"docs": 1})
    failed = reg.finish_run(
        "run:1", finished_at=T11, status="failed", stats={"docs": 1, "error": "boom"}
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.finished_at == T11
    assert failed.stats == {"docs": 1, "error": "boom"}


def test_recent_newest_first(reg: RunRegistry) -> None:
    """recent orders runs newest-first by started_at and honours limit (§9.7)."""
    reg.record_run("run:1", kind="ingest", started_at=T10)
    reg.record_run("run:2", kind="ingest", started_at=T11)
    reg.record_run("run:3", kind="ingest", started_at=T09)

    assert [r.run_id for r in reg.recent()] == ["run:2", "run:1", "run:3"]
    assert [r.run_id for r in reg.recent(limit=2)] == ["run:2", "run:1"]


def test_re_record_is_idempotent_upsert(reg: RunRegistry) -> None:
    """Re-recording the same run_id updates fields in place — no duplicate row (§9.7)."""
    reg.record_run("run:1", kind="ingest", started_at=T10)
    reg.finish_run("run:1", finished_at=T11)  # mark finished first
    reg.record_run("run:1", kind="reindex", started_at=T12, stats={"docs": 5})

    assert len(reg.recent()) == 1  # single row
    got = reg.get_run("run:1")
    assert got.kind == "reindex"
    assert got.started_at == T12
    assert got.status == "running"  # a fresh record resets status
    assert got.finished_at is None  # ... and clears the earlier finish stamp
    assert got.stats == {"docs": 5}


def test_stats_round_trip_json(reg: RunRegistry) -> None:
    """stats survives a JSON encode/decode round-trip, incl. nested RU/EN text (§9.7)."""
    stats = {
        "docs": 3,
        "entities": 42,
        "ratio": 0.75,
        "labels": ["a", "b"],
        "nested": {"note": "значение / value"},
    }
    reg.record_run("run:1", kind="ingest", started_at=T10, stats=stats)
    got = reg.get_run("run:1")
    assert got.stats == stats
    assert got.as_dict()["stats"] == stats


def test_unknown_run_returns_none(reg: RunRegistry) -> None:
    """Unknown ids yield None for both get_run and finish_run (§9.7)."""
    assert reg.get_run("missing") is None
    assert reg.finish_run("missing", finished_at=T11) is None


def test_recent_filters_by_kind(reg: RunRegistry) -> None:
    """recent(kind=...) filters to one run kind, still newest-first (§9.7)."""
    reg.record_run("a", kind="ingest", started_at=T10)
    reg.record_run("b", kind="reindex", started_at=T11)
    reg.record_run("c", kind="ingest", started_at=T12)

    assert [r.run_id for r in reg.recent(kind="ingest")] == ["c", "a"]
    assert [r.run_id for r in reg.recent(kind="reindex")] == ["b"]
    assert reg.recent(kind="nope") == []


def test_invalid_status_rejected(reg: RunRegistry) -> None:
    """Both record_run and finish_run reject an unknown status (§9.7)."""
    with pytest.raises(ValueError):
        reg.record_run("run:1", kind="ingest", started_at=T10, status="bogus")
    reg.record_run("run:1", kind="ingest", started_at=T10)
    with pytest.raises(ValueError):
        reg.finish_run("run:1", finished_at=T11, status="bogus")


def test_started_at_index_created_by_migrate(reg: RunRegistry) -> None:
    """migrate() materialises the started_at index backing recent()'s ORDER BY (§9.7).

    Perf-only optimisation: the index must exist on the exact column recent() sorts by,
    proving :meth:`RunRegistry.migrate` (``create_all``) actually created it.
    """
    indexes = inspect(reg.engine).get_indexes("pipeline_runs")
    by_name = {ix["name"]: ix for ix in indexes}
    assert "ix_pipeline_runs_started" in by_name
    assert by_name["ix_pipeline_runs_started"]["column_names"] == ["started_at"]


def test_recent_ordering_unchanged_with_index(reg: RunRegistry) -> None:
    """The index is behaviour-preserving: recent() still returns the identical order.

    Includes a started_at tie (T10) to lock in the ``run_id DESC`` secondary tie-break.
    """
    reg.record_run("run:1", kind="ingest", started_at=T10)
    reg.record_run("run:2", kind="ingest", started_at=T10)  # tie on started_at
    reg.record_run("run:3", kind="ingest", started_at=T11)
    reg.record_run("run:4", kind="ingest", started_at=T09)

    # newest started_at first; ties broken by descending run_id (run:2 before run:1)
    assert [r.run_id for r in reg.recent()] == ["run:3", "run:2", "run:1", "run:4"]
    assert [r.run_id for r in reg.recent(limit=2)] == ["run:3", "run:2"]
