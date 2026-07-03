"""Tests for §14.10 ingest pipeline-step timeline (:mod:`pipeline_steps`).

Тесты хронологии шагов конвейера для ответа ``GET /ingest/jobs/{id}``.
"""

from __future__ import annotations

from api_gateway.pipeline_steps import (
    PIPELINE_STEPS,
    PipelineProgress,
    StepState,
    build_progress,
    compute_progress,
    derive_status,
    init_steps,
)


def _steps_with(statuses: list[str]) -> tuple[StepState, ...]:
    """Build a 12-step tuple applying ``statuses`` to the §9.1 stage names."""

    assert len(statuses) == len(PIPELINE_STEPS)
    return tuple(
        StepState(name=name, status=status)
        for name, status in zip(PIPELINE_STEPS, statuses, strict=True)
    )


def test_pipeline_has_twelve_stages() -> None:
    assert len(PIPELINE_STEPS) == 12


def test_pipeline_stage_names_are_the_9_1_stages() -> None:
    assert PIPELINE_STEPS == (
        "register",
        "parse",
        "store",
        "chunk",
        "extract",
        "normalize",
        "resolve",
        "validate",
        "upsert",
        "index",
        "gap",
        "eval",
    )


def test_init_steps_all_pending() -> None:
    steps = init_steps()
    assert len(steps) == 12
    assert all(s.status == "pending" for s in steps)
    assert tuple(s.name for s in steps) == PIPELINE_STEPS


def test_compute_progress_initial_is_zero() -> None:
    assert compute_progress(init_steps()) == 0.0


def test_compute_progress_all_succeeded_is_one() -> None:
    steps = _steps_with(["succeeded"] * 12)
    assert compute_progress(steps) == 1.0


def test_compute_progress_half() -> None:
    # 6 succeeded of 12 -> 0.5.
    statuses = ["succeeded"] * 6 + ["pending"] * 6
    assert compute_progress(_steps_with(statuses)) == 0.5


def test_compute_progress_empty_is_zero() -> None:
    assert compute_progress(()) == 0.0


def test_skipped_counts_toward_progress() -> None:
    # 11 succeeded + 1 skipped -> fully done.
    statuses = ["succeeded"] * 11 + ["skipped"]
    assert compute_progress(_steps_with(statuses)) == 1.0


def test_derive_status_failed_wins() -> None:
    statuses = ["succeeded"] * 11 + ["failed"]
    assert derive_status(_steps_with(statuses)) == "failed"


def test_derive_status_failed_wins_over_running() -> None:
    statuses = ["running"] * 6 + ["failed"] + ["pending"] * 5
    assert derive_status(_steps_with(statuses)) == "failed"


def test_derive_status_all_succeeded() -> None:
    assert derive_status(_steps_with(["succeeded"] * 12)) == "succeeded"


def test_derive_status_all_done_with_skipped_is_succeeded() -> None:
    statuses = ["succeeded"] * 11 + ["skipped"]
    assert derive_status(_steps_with(statuses)) == "succeeded"


def test_derive_status_mix_pending_and_running() -> None:
    statuses = ["running"] + ["pending"] * 11
    assert derive_status(_steps_with(statuses)) == "running"


def test_derive_status_some_done_is_running() -> None:
    # No running step, but some done and some pending -> still running.
    statuses = ["succeeded"] * 3 + ["pending"] * 9
    assert derive_status(_steps_with(statuses)) == "running"


def test_derive_status_all_pending_is_queued() -> None:
    assert derive_status(init_steps()) == "queued"


def test_derive_status_empty_is_queued() -> None:
    assert derive_status(()) == "queued"


def test_step_state_as_dict() -> None:
    assert StepState(name="parse", status="running").as_dict() == {
        "name": "parse",
        "status": "running",
    }


def test_build_progress_running_payload() -> None:
    statuses = ["succeeded"] * 6 + ["running"] + ["pending"] * 5
    prog = build_progress(_steps_with(statuses))
    assert isinstance(prog, PipelineProgress)
    assert prog.status == "running"
    assert prog.progress == 0.5
    assert len(prog.steps) == 12


def test_pipeline_progress_as_dict_shape() -> None:
    prog = build_progress(init_steps())
    payload = prog.as_dict()
    assert payload["status"] == "queued"
    assert payload["progress"] == 0.0
    assert isinstance(payload["steps"], list)
    assert payload["steps"][0] == {"name": "register", "status": "pending"}
    assert len(payload["steps"]) == 12


def test_build_progress_succeeded_full() -> None:
    prog = build_progress(_steps_with(["succeeded"] * 12))
    assert prog.status == "succeeded"
    assert prog.progress == 1.0


def test_frozen_dataclasses_are_immutable() -> None:
    step = StepState(name="parse", status="pending")
    try:
        step.status = "running"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("StepState should be frozen")
