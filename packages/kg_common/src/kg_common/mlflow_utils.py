"""Optional MLflow experiment tracking (§18.4).

MLflow (Apache-2.0, разрешён §7.5) может быть *не установлен* — поэтому он здесь
строго опционален. :func:`start_run` использует настоящий MLflow, только если он
импортируется И задан ``mlflow_tracking_uri`` (см.
:mod:`kg_common.config`); иначе он откатывается на :class:`InMemoryRecorder`,
так что трекинг **всегда работает офлайн** и в тестах — без сети и без mlflow.

An experiment "run" records params, metrics and tags plus provenance
(``git_sha`` + ``dataset_version``). The ``run_id`` is *deterministic* — a hash
of ``(experiment, git_sha, dataset_version)`` — so re-runs of the same code over
the same dataset land on the same id (без ``datetime.now`` / ``uuid``).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from kg_common.config import get_settings

# -- constants (§18.4 tracked experiment surfaces) ------------------------
#: Три отслеживаемых эксперимента: извлечение, поиск, синтез ответа.
EXPERIMENTS: tuple[str, ...] = ("extraction", "retrieval", "answer")

#: Разделитель полей для детерминированного ``run_id`` (unit separator).
_FIELD_SEP = "\x1f"
#: Длина усечённого hex-дайджеста, используемого как ``run_id``.
_RUN_ID_LEN = 16

__all__ = [
    "EXPERIMENTS",
    "ExperimentRun",
    "InMemoryRecorder",
    "Recorder",
    "RunHandle",
    "compute_run_id",
    "end",
    "log_metrics",
    "log_params",
    "set_tags",
    "start_run",
]


@runtime_checkable
class Recorder(Protocol):
    """Backend-agnostic sink for a run (§18.4) — mlflow или in-memory.

    Реализация принимает произвольные словари; :class:`RunHandle` нормализует
    ключи к строкам перед передачей.
    """

    def log_params(self, params: Mapping[str, Any]) -> None:
        """Записать параметры прогона (конфиг, модель, гиперпараметры)."""
        ...

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        """Записать числовые метрики (recall, latency, f1, …)."""
        ...

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Проставить теги прогона (git_sha, dataset_version, env, …)."""
        ...


class InMemoryRecorder:
    """Offline :class:`Recorder` — накапливает всё в памяти (§18.4 fallback).

    Используется, когда mlflow недоступен: делает трекинг детерминированным и
    полностью пригодным для тестов без внешних зависимостей.
    """

    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self.metrics: dict[str, float] = {}
        self.tags: dict[str, str] = {}
        self.ended: bool = False

    def log_params(self, params: Mapping[str, Any]) -> None:
        self.params.update({str(k): v for k, v in params.items()})

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self.metrics.update({str(k): float(v) for k, v in metrics.items()})

    def set_tags(self, tags: Mapping[str, str]) -> None:
        self.tags.update({str(k): str(v) for k, v in tags.items()})

    def end(self) -> None:
        """Пометить прогон завершённым (idempotent)."""
        self.ended = True


class _MlflowRecorder:
    """Adapter over the real ``mlflow`` module (§18.4 online path).

    Стартует прогон при создании и проксирует вызовы в mlflow. Создаётся только
    если mlflow импортируется И задан tracking uri; иначе — :class:`InMemoryRecorder`.
    """

    def __init__(self, mlflow: Any, experiment: str, run_id: str, tracking_uri: str) -> None:
        self._mlflow = mlflow
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment)
        mlflow.start_run(run_name=run_id)

    def log_params(self, params: Mapping[str, Any]) -> None:
        self._mlflow.log_params(dict(params))

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._mlflow.log_metrics({str(k): float(v) for k, v in metrics.items()})

    def set_tags(self, tags: Mapping[str, str]) -> None:
        self._mlflow.set_tags({str(k): str(v) for k, v in tags.items()})

    def end(self) -> None:
        self._mlflow.end_run()


@dataclass(frozen=True)
class ExperimentRun:
    """Immutable snapshot of one tracked run (§18.4).

    Плоская сериализуемая запись прогона: эксперимент, детерминированный id,
    накопленные params/metrics/tags и происхождение (``git_sha`` +
    ``dataset_version``).
    """

    experiment: str
    run_id: str
    params: Mapping[str, Any]
    metrics: Mapping[str, float]
    tags: Mapping[str, str]
    git_sha: str
    dataset_version: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready copy (shallow, defensive)."""
        return {
            "experiment": self.experiment,
            "run_id": self.run_id,
            "params": dict(self.params),
            "metrics": dict(self.metrics),
            "tags": dict(self.tags),
            "git_sha": self.git_sha,
            "dataset_version": self.dataset_version,
        }


def compute_run_id(experiment: str, git_sha: str, dataset_version: str) -> str:
    """Deterministic ``run_id`` from ``(experiment, git_sha, dataset_version)``.

    Никаких ``datetime.now`` / ``uuid`` — тот же вход даёт тот же id (§18.4),
    что делает повторные прогоны идемпотентными.
    """
    payload = _FIELD_SEP.join((experiment, git_sha, dataset_version))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_RUN_ID_LEN]


class RunHandle:
    """Handle over one open run (§18.4) — forwards to a :class:`Recorder`.

    Накапливает params/metrics/tags локально (для :class:`ExperimentRun`) и
    одновременно проксирует их в recorder. :meth:`end` финализирует прогон.
    """

    def __init__(
        self,
        experiment: str,
        run_id: str,
        recorder: Recorder,
        *,
        git_sha: str = "",
        dataset_version: str = "",
    ) -> None:
        self.experiment = experiment
        self.run_id = run_id
        self.recorder = recorder
        self.git_sha = git_sha
        self.dataset_version = dataset_version
        self._params: dict[str, Any] = {}
        self._metrics: dict[str, float] = {}
        self._tags: dict[str, str] = {}
        self._ended = False

    def _check_open(self) -> None:
        if self._ended:
            raise RuntimeError(f"run {self.run_id!r} already ended")

    def log_params(self, params: Mapping[str, Any]) -> RunHandle:
        """Record params locally and forward to the recorder."""
        self._check_open()
        self._params.update({str(k): v for k, v in params.items()})
        self.recorder.log_params(params)
        return self

    def log_metrics(self, metrics: Mapping[str, float]) -> RunHandle:
        """Record metrics locally and forward to the recorder."""
        self._check_open()
        self._metrics.update({str(k): float(v) for k, v in metrics.items()})
        self.recorder.log_metrics(metrics)
        return self

    def set_tags(self, tags: Mapping[str, str]) -> RunHandle:
        """Record tags locally and forward to the recorder."""
        self._check_open()
        self._tags.update({str(k): str(v) for k, v in tags.items()})
        self.recorder.set_tags(tags)
        return self

    @property
    def ended(self) -> bool:
        """Whether :meth:`end` has been called."""
        return self._ended

    @property
    def run(self) -> ExperimentRun:
        """Build an :class:`ExperimentRun` snapshot from current state."""
        return ExperimentRun(
            experiment=self.experiment,
            run_id=self.run_id,
            params=dict(self._params),
            metrics=dict(self._metrics),
            tags=dict(self._tags),
            git_sha=self.git_sha,
            dataset_version=self.dataset_version,
        )

    def end(self) -> ExperimentRun:
        """Finalize the run (idempotent) and return its snapshot."""
        if not self._ended:
            self._ended = True
            finish = getattr(self.recorder, "end", None)
            if callable(finish):
                finish()
        return self.run


def _resolve_recorder(experiment: str, run_id: str) -> Recorder:
    """Pick the mlflow recorder if usable, else the offline in-memory one."""
    tracking_uri = get_settings().mlflow_tracking_uri
    if tracking_uri:
        try:
            import mlflow

            return _MlflowRecorder(mlflow, experiment, run_id, tracking_uri)
        except Exception:
            # mlflow отсутствует или бэкенд недоступен → офлайн-откат (§18.4).
            return InMemoryRecorder()
    return InMemoryRecorder()


def start_run(
    experiment: str,
    *,
    recorder: Recorder | None = None,
    git_sha: str = "",
    dataset_version: str = "",
) -> RunHandle:
    """Open a tracked run for ``experiment`` (§18.4).

    Uses real mlflow only if importable *and* a tracking uri is configured;
    otherwise falls back to :class:`InMemoryRecorder`, so it always works offline.
    ``run_id`` детерминирован (:func:`compute_run_id`).
    """
    if experiment not in EXPERIMENTS:
        raise ValueError(f"unknown experiment {experiment!r}; expected one of {EXPERIMENTS}")
    run_id = compute_run_id(experiment, git_sha, dataset_version)
    if recorder is None:
        recorder = _resolve_recorder(experiment, run_id)
    return RunHandle(
        experiment,
        run_id,
        recorder,
        git_sha=git_sha,
        dataset_version=dataset_version,
    )


def log_params(handle: RunHandle, params: Mapping[str, Any]) -> RunHandle:
    """Helper: record params on ``handle`` (functional API)."""
    return handle.log_params(params)


def log_metrics(handle: RunHandle, metrics: Mapping[str, float]) -> RunHandle:
    """Helper: record metrics on ``handle`` (functional API)."""
    return handle.log_metrics(metrics)


def set_tags(handle: RunHandle, tags: Mapping[str, str]) -> RunHandle:
    """Helper: record tags on ``handle`` (functional API)."""
    return handle.set_tags(tags)


def end(handle: RunHandle) -> ExperimentRun:
    """Helper: finalize ``handle`` and return its snapshot."""
    return handle.end()
