"""Ingest job pipeline-step timeline for §14.10 ``GET /ingest/jobs/{id}``.

Хронология шагов конвейера обработки для ответа ``GET /ingest/jobs/{id}``
(§14.10).

The SQLAlchemy ``JobStore`` only persists a coarse ``done``/``total`` fraction —
it does **not** track the twelve named §9.1 pipeline stages. This module supplies
the small, pure building blocks the endpoint needs to render the richer
``steps``/``progress``/``status`` payload from an in-flight step list:

* :data:`PIPELINE_STEPS`   — the twelve ordered §9.1 stage names.
* :class:`StepState`       — one ``(name, status)`` stage, frozen.
* :class:`PipelineProgress`— the full ``steps``/``status``/``progress`` payload.
* :func:`init_steps`       — a fresh tuple with every stage ``pending``.
* :func:`compute_progress` — fraction of stages ``succeeded`` **or** ``skipped``.
* :func:`derive_status`    — roll the per-step statuses up to a job status.
* :func:`build_progress`   — assemble a :class:`PipelineProgress` from steps.

A ``skipped`` stage counts as *done* for both progress and status: an optional
stage that the pipeline chose not to run must not stall the job at ``running``.
"""

from __future__ import annotations

from dataclasses import dataclass

# The twelve §9.1 ingest stages, in execution order.
PIPELINE_STEPS: tuple[str, ...] = (
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

# Per-step statuses that mean the stage will run no further (counts as done).
_DONE_STATUSES: frozenset[str] = frozenset({"succeeded", "skipped"})


@dataclass(frozen=True, slots=True)
class StepState:
    """One pipeline stage: its §9.1 ``name`` and current ``status``.

    Один шаг конвейера — имя стадии (§9.1) и его текущий статус. :meth:`as_dict`
    даёт вид для JSON-ответа/тестов.
    """

    name: str
    status: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status}


@dataclass(frozen=True, slots=True)
class PipelineProgress:
    """The ``steps``/``status``/``progress`` payload for §14.10.

    Полезная нагрузка ответа ``GET /ingest/jobs/{id}``: список шагов, сводный
    статус задания и доля выполнения ``[0.0, 1.0]``.
    """

    steps: tuple[StepState, ...]
    status: str
    progress: float

    def as_dict(self) -> dict[str, object]:
        return {
            "steps": [s.as_dict() for s in self.steps],
            "status": self.status,
            "progress": self.progress,
        }


def init_steps() -> tuple[StepState, ...]:
    """Return a fresh step tuple with every §9.1 stage ``pending``.

    Начальное состояние конвейера — все двенадцать стадий в статусе ``pending``.
    """

    return tuple(StepState(name=name, status="pending") for name in PIPELINE_STEPS)


def compute_progress(steps: tuple[StepState, ...]) -> float:
    """Fraction of stages that are done (``succeeded`` or ``skipped``).

    Доля завершённых стадий: ``(succeeded + skipped) / total``. Пустой список
    даёт ``0.0``.
    """

    if not steps:
        return 0.0
    done = sum(1 for s in steps if s.status in _DONE_STATUSES)
    return done / len(steps)


def derive_status(steps: tuple[StepState, ...]) -> str:
    """Roll per-step statuses up to a single job status.

    Сводный статус задания: ``failed`` если есть провал; иначе ``succeeded`` если
    все стадии завершены; иначе ``running`` если есть выполняемая/частично
    выполненные; иначе ``queued``.
    """

    if not steps:
        return "queued"
    if any(s.status == "failed" for s in steps):
        return "failed"
    if all(s.status in _DONE_STATUSES for s in steps):
        return "succeeded"
    any_running = any(s.status == "running" for s in steps)
    any_done = any(s.status in _DONE_STATUSES for s in steps)
    if any_running or any_done:
        return "running"
    return "queued"


def build_progress(steps: tuple[StepState, ...]) -> PipelineProgress:
    """Assemble a :class:`PipelineProgress` from a step tuple.

    Собрать полезную нагрузку §14.10 из списка шагов: статус и доля выполнения
    выводятся из :func:`derive_status` и :func:`compute_progress`.
    """

    return PipelineProgress(
        steps=steps,
        status=derive_status(steps),
        progress=compute_progress(steps),
    )
