"""Canonical pipeline-stage DAG — эталонный граф стадий пайплайна (§9.1).

Declares the §9.1 ingestion/index flow as *data* so every consumer — the job
status view, the scheduler, and the retrieval-eval gate — reads one source of
truth instead of hard-coding stage names. Each stage is a frozen
:class:`PipelineStage` (``key``, ``deps``, ``description``); the module offers
four pure, side-effect-free helpers over that set:

* :func:`pipeline_steps` — the canonical ordered tuple of stages.
* :func:`topo_steps`     — a dependency-respecting linearisation of the keys.
* :func:`downstream_of_failure` — every transitive dependent that a failure must
  skip («что придётся пропустить при сбое стадии»).
* :func:`job_step_view` — per-step ``done``/``current``/``pending`` labelling for
  a running job.

Canonical flow (§9.1)::

    register_source → docling_parse → store_parsed → chunk → extract
        → units_normalization → entity_resolution → schema_validation
        → graph_upsert → (qdrant_indexing, opensearch_indexing)
        → gap_scan
        → retrieval_eval

``graph_upsert`` gates on ``schema_validation``; both index stages fan out from
``schema_validation``/``graph_upsert``; ``retrieval_eval`` gates on *both* index
stages. Everything here is deterministic: order follows declaration order with a
stable topological sort, so the records are pure functions of the stage set.

Public API:

* :class:`PipelineStage` — frozen stage with :meth:`PipelineStage.as_dict`.
* :func:`pipeline_steps`, :func:`topo_steps`, :func:`downstream_of_failure`,
  :func:`job_step_view`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PipelineStage",
    "pipeline_steps",
    "topo_steps",
    "downstream_of_failure",
    "job_step_view",
]


@dataclass(frozen=True, slots=True)
class PipelineStage:
    """Immutable pipeline stage — неизменяемая стадия пайплайна (§9.1).

    ``key`` is the stable machine name; ``deps`` are the keys that must complete
    before this stage may run; ``description`` is a short human label. ``deps``
    is a tuple so the record is hashable and order-stable.
    """

    key: str
    deps: tuple[str, ...]
    description: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — стадия как словарь (§9.1)."""
        return {
            "key": self.key,
            "deps": list(self.deps),
            "description": self.description,
        }


# Canonical §9.1 flow, in declaration order. Each stage lists the stages that
# must finish before it may start. Declaration order is already a valid
# topological order, which keeps the stable sort below intuitive.
_STAGES: tuple[PipelineStage, ...] = (
    PipelineStage(
        "register_source",
        (),
        "Register the source document / регистрация источника",
    ),
    PipelineStage(
        "docling_parse",
        ("register_source",),
        "Parse layout with Docling / разбор макета Docling",
    ),
    PipelineStage(
        "store_parsed",
        ("docling_parse",),
        "Persist the parsed artifact / сохранение разобранного артефакта",
    ),
    PipelineStage(
        "chunk",
        ("store_parsed",),
        "Split into retrieval chunks / нарезка на чанки",
    ),
    PipelineStage(
        "extract",
        ("chunk",),
        "Extract entities and relations / извлечение сущностей и связей",
    ),
    PipelineStage(
        "units_normalization",
        ("extract",),
        "Normalise units of measure / нормализация единиц измерения",
    ),
    PipelineStage(
        "entity_resolution",
        ("units_normalization",),
        "Resolve and dedupe entities / разрешение сущностей",
    ),
    PipelineStage(
        "schema_validation",
        ("entity_resolution",),
        "Validate against the graph schema / проверка по схеме графа",
    ),
    PipelineStage(
        "graph_upsert",
        ("schema_validation",),
        "Upsert nodes and edges into the KG / запись в граф знаний",
    ),
    PipelineStage(
        "qdrant_indexing",
        ("graph_upsert", "schema_validation"),
        "Index vectors into Qdrant / индексация векторов в Qdrant",
    ),
    PipelineStage(
        "opensearch_indexing",
        ("graph_upsert", "schema_validation"),
        "Index text into OpenSearch / индексация текста в OpenSearch",
    ),
    PipelineStage(
        "gap_scan",
        ("graph_upsert",),
        "Scan the graph for knowledge gaps / поиск пробелов знаний",
    ),
    PipelineStage(
        "retrieval_eval",
        ("qdrant_indexing", "opensearch_indexing"),
        "Evaluate retrieval quality / оценка качества поиска",
    ),
)


def pipeline_steps() -> tuple[PipelineStage, ...]:
    """Return the canonical §9.1 stages — эталонные стадии (§9.1).

    The tuple is in declaration order, which is itself a valid dependency
    order (every dependency is declared before the stage that needs it).
    """
    return _STAGES


def _stage_index() -> dict[str, PipelineStage]:
    """Map ``key`` → stage — индекс стадий по ключу (§9.1)."""
    return {stage.key: stage for stage in _STAGES}


def topo_steps() -> list[str]:
    """Return keys in dependency-respecting order — топологический порядок (§9.1).

    A stable Kahn linearisation: among stages whose dependencies are already
    emitted, the one declared earliest in :func:`pipeline_steps` goes first. The
    result is deterministic and places every dependency before its dependents.
    """
    order = [stage.key for stage in _STAGES]  # declaration = tie-break order
    index = _stage_index()
    remaining = set(order)
    emitted: list[str] = []
    emitted_set: set[str] = set()
    while remaining:
        progressed = False
        for key in order:
            if key not in remaining:
                continue
            if all(dep in emitted_set for dep in index[key].deps):
                emitted.append(key)
                emitted_set.add(key)
                remaining.discard(key)
                progressed = True
        if not progressed:  # pragma: no cover - guards against a cyclic DAG
            raise ValueError(f"cycle among stages: {sorted(remaining)}")
    return emitted


def downstream_of_failure(failed_key: str) -> list[str]:
    """Stages to skip if ``failed_key`` fails — что пропустить при сбое (§9.1).

    Returns every stage that transitively depends on ``failed_key`` (its
    dependents, and their dependents, and so on), excluding ``failed_key``
    itself. The result is in topological order. Raises :class:`KeyError` for an
    unknown key.
    """
    index = _stage_index()
    if failed_key not in index:
        raise KeyError(failed_key)
    blocked = {failed_key}
    # Walk stages in topo order so a dependent is only added after its own deps
    # have been considered — one pass suffices.
    for key in topo_steps():
        if key == failed_key:
            continue
        if any(dep in blocked for dep in index[key].deps):
            blocked.add(key)
    return [key for key in topo_steps() if key in blocked and key != failed_key]


def job_step_view(current_key: str) -> list[dict]:
    """Label each stage for a running job — статус стадий задания (§9.1).

    Walks :func:`topo_steps` and marks each stage ``done`` (before the current
    one), ``current`` (equals ``current_key``), or ``pending`` (after it). Raises
    :class:`KeyError` for an unknown ``current_key``.
    """
    index = _stage_index()
    if current_key not in index:
        raise KeyError(current_key)
    order = topo_steps()
    current_pos = order.index(current_key)
    view: list[dict] = []
    for pos, key in enumerate(order):
        if pos < current_pos:
            status = "done"
        elif pos == current_pos:
            status = "current"
        else:
            status = "pending"
        view.append(
            {
                "key": key,
                "status": status,
                "description": index[key].description,
            }
        )
    return view
