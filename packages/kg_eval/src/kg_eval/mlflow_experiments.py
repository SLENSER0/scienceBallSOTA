"""Named MLflow experiment specs + typed convenience wrappers (§18.4).

Тонкий слой НАД :mod:`kg_common.mlflow_utils`: переиспользует
``EXPERIMENTS``/``start_run`` (без правок) и добавляет *декларативный реестр* трёх
отслеживаемых поверхностей — извлечение (extraction), поиск (retrieval), синтез
ответа (answer). Каждый :class:`ExperimentSpec` перечисляет ожидаемые
``tracked_params`` и ``tracked_metrics``; удобные обёртки
:func:`log_extraction_run` / :func:`log_retrieval_run` / :func:`log_answer_run`
открывают нужный прогон, логируют params+metrics и возвращают снимок
:class:`~kg_common.mlflow_utils.ExperimentRun`.

The registry is *documentation of expected fields*, not a filter: an unknown
metric is tolerated (logged as-is, no error), so new metrics never break tracking.
Всё работает офлайн — при ``recorder=None`` ``start_run`` откатывается на
:class:`~kg_common.mlflow_utils.InMemoryRecorder` (без сети и без mlflow).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kg_common.mlflow_utils import EXPERIMENTS, ExperimentRun, Recorder, start_run

# -- experiment name constants (must match mlflow_utils.EXPERIMENTS) -------
#: Извлечение сущностей/связей из текста (§18.4).
EXTRACTION_EXPERIMENT: str = EXPERIMENTS[0]
#: Поиск релевантных чанков/экспериментов (§18.4).
RETRIEVAL_EXPERIMENT: str = EXPERIMENTS[1]
#: Синтез финального ответа поверх найденного контекста (§18.4).
ANSWER_EXPERIMENT: str = EXPERIMENTS[2]

__all__ = [
    "ALL_SPECS",
    "ANSWER_EXPERIMENT",
    "ANSWER_SPEC",
    "EXTRACTION_EXPERIMENT",
    "EXTRACTION_SPEC",
    "RETRIEVAL_EXPERIMENT",
    "RETRIEVAL_SPEC",
    "ExperimentSpec",
    "log_answer_run",
    "log_extraction_run",
    "log_retrieval_run",
    "spec_for",
]


@dataclass(frozen=True)
class ExperimentSpec:
    """Declarative spec for one tracked experiment (§18.4).

    Именованная поверхность трекинга: как её эксперимент называется в mlflow и
    какие ``params``/``metrics`` для неё ожидаемы. Реестр — документация, а не
    фильтр: unknown fields are tolerated by the wrappers (logged as-is).
    """

    name: str
    tracked_params: tuple[str, ...]
    tracked_metrics: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready copy (tuples → lists)."""
        return {
            "name": self.name,
            "tracked_params": list(self.tracked_params),
            "tracked_metrics": list(self.tracked_metrics),
        }


#: Извлечение: LLM-конфиг → качество сущностей/связей (§18.4).
EXTRACTION_SPEC = ExperimentSpec(
    name=EXTRACTION_EXPERIMENT,
    tracked_params=(
        "model",
        "temperature",
        "prompt_version",
        "schema_version",
        "chunk_size",
    ),
    tracked_metrics=(
        "entity_precision",
        "entity_recall",
        "entity_f1",
        "relation_f1",
        "latency_ms",
    ),
)

#: Поиск: ретривер/эмбеддинги → ранжирующие метрики (§18.4, ср. §18.6).
RETRIEVAL_SPEC = ExperimentSpec(
    name=RETRIEVAL_EXPERIMENT,
    tracked_params=(
        "retriever",
        "embedding_model",
        "k",
        "hybrid_weight",
        "rerank",
    ),
    tracked_metrics=(
        "recall_at_k",
        "precision_at_k",
        "mrr",
        "ndcg_at_k",
        "hit_at_k",
    ),
)

#: Синтез ответа: генератор → верность/релевантность (§18.4).
ANSWER_SPEC = ExperimentSpec(
    name=ANSWER_EXPERIMENT,
    tracked_params=(
        "model",
        "temperature",
        "prompt_version",
        "top_k",
    ),
    tracked_metrics=(
        "faithfulness",
        "answer_relevance",
        "groundedness",
        "latency_ms",
    ),
)

#: Реестр всех трёх spec'ов (§18.4) — по порядку ``EXPERIMENTS``.
ALL_SPECS: tuple[ExperimentSpec, ...] = (EXTRACTION_SPEC, RETRIEVAL_SPEC, ANSWER_SPEC)

_SPECS_BY_NAME: Mapping[str, ExperimentSpec] = {s.name: s for s in ALL_SPECS}


def spec_for(name: str) -> ExperimentSpec:
    """Look up the :class:`ExperimentSpec` for ``name`` (§18.4)."""
    try:
        return _SPECS_BY_NAME[name]
    except KeyError:
        raise ValueError(
            f"unknown experiment {name!r}; expected one of {tuple(_SPECS_BY_NAME)}"
        ) from None


def _log_run(
    spec: ExperimentSpec,
    metrics: Mapping[str, float],
    *,
    params: Mapping[str, Any] | None = None,
    recorder: Recorder | None = None,
) -> ExperimentRun:
    """Open ``spec``'s run, log params+metrics, finalize and return the snapshot.

    Неизвестные метрики/параметры допускаются (логируются как есть). При
    ``recorder=None`` используется офлайн :class:`InMemoryRecorder`.
    """
    handle = start_run(spec.name, recorder=recorder)
    if params:
        handle.log_params(params)
    if metrics:
        handle.log_metrics(metrics)
    return handle.end()


def log_extraction_run(
    metrics: Mapping[str, float],
    *,
    params: Mapping[str, Any] | None = None,
    recorder: Recorder | None = None,
) -> ExperimentRun:
    """Log an extraction run (§18.4) and return its :class:`ExperimentRun` snapshot."""
    return _log_run(EXTRACTION_SPEC, metrics, params=params, recorder=recorder)


def log_retrieval_run(
    metrics: Mapping[str, float],
    *,
    params: Mapping[str, Any] | None = None,
    recorder: Recorder | None = None,
) -> ExperimentRun:
    """Log a retrieval run (§18.4) and return its :class:`ExperimentRun` snapshot."""
    return _log_run(RETRIEVAL_SPEC, metrics, params=params, recorder=recorder)


def log_answer_run(
    metrics: Mapping[str, float],
    *,
    params: Mapping[str, Any] | None = None,
    recorder: Recorder | None = None,
) -> ExperimentRun:
    """Log an answer-synthesis run (§18.4) and return its :class:`ExperimentRun` snapshot."""
    return _log_run(ANSWER_SPEC, metrics, params=params, recorder=recorder)
