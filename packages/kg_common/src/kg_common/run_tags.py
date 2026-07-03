"""Run tags — метки прогонов, связывающие документ/источник/задание (§9.8).

Each ingest run (Dagster run) carries a small, flat set of *run tags* — string
key/value pairs that link the run back to the document, source and ingest job it
processed, plus how it was triggered. Tags use two namespaces so they never clash
with framework-internal keys:

* ``kg/*``      — our domain keys: ``kg/doc_id``, ``kg/source_id``,
  ``kg/ingest_job_id``, ``kg/run_type``.
* ``dagster/*`` — orchestrator keys the scheduler also understands:
  ``dagster/partition``, ``dagster/schedule_name``.

Everything here is pure and side-effect free: no I/O, no wall-clock, no globals.
Missing (``None``) fields are simply omitted, and every value is string-coerced so
the resulting mapping is always ``dict[str, str]`` — ready to hand to the run
storage as-is.

Public API:

* :class:`RunTags`      — frozen record with :meth:`RunTags.as_dict`.
* :func:`build_run_tags` — build a namespaced ``dict[str, str]`` of tags.
* :func:`matches_tags`   — does a run's tags satisfy a query (all kv present/equal)?
* :func:`filter_runs`    — keep only runs whose tags match a query.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "DOC_ID_KEY",
    "SOURCE_ID_KEY",
    "INGEST_JOB_ID_KEY",
    "RUN_TYPE_KEY",
    "PARTITION_KEY",
    "SCHEDULE_NAME_KEY",
    "RunTags",
    "build_run_tags",
    "matches_tags",
    "filter_runs",
]


# --------------------------------------------------------------------------- #
# Namespaced tag keys — пространства имён ключей                               #
# --------------------------------------------------------------------------- #

#: Document the run processed — идентификатор документа.
DOC_ID_KEY: str = "kg/doc_id"

#: Source the document came from — идентификатор источника.
SOURCE_ID_KEY: str = "kg/source_id"

#: Ingest job that owns the run — идентификатор задания загрузки.
INGEST_JOB_ID_KEY: str = "kg/ingest_job_id"

#: How the run was triggered — тип запуска (``manual`` / ``scheduled`` / …).
RUN_TYPE_KEY: str = "kg/run_type"

#: Dagster partition key — ключ партиции оркестратора.
PARTITION_KEY: str = "dagster/partition"

#: Dagster schedule name — имя расписания оркестратора.
SCHEDULE_NAME_KEY: str = "dagster/schedule_name"

#: Default trigger type when none is given — тип запуска по умолчанию.
DEFAULT_RUN_TYPE: str = "manual"


# --------------------------------------------------------------------------- #
# Tag record — запись меток                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RunTags:
    """A resolved set of run tags — разрешённый набор меток прогона.

    ``run_type`` always has a value; the remaining fields are optional and omitted
    from :meth:`as_dict` when ``None``.
    """

    run_type: str = DEFAULT_RUN_TYPE
    doc_id: str | None = None
    source_id: str | None = None
    ingest_job_id: str | None = None
    partition_key: str | None = None
    schedule_name: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Render as a namespaced ``dict[str, str]`` — отображение меток.

        ``None`` fields are omitted; every emitted value is string-coerced.
        """
        pairs: list[tuple[str, object | None]] = [
            (DOC_ID_KEY, self.doc_id),
            (SOURCE_ID_KEY, self.source_id),
            (INGEST_JOB_ID_KEY, self.ingest_job_id),
            (RUN_TYPE_KEY, self.run_type),
            (PARTITION_KEY, self.partition_key),
            (SCHEDULE_NAME_KEY, self.schedule_name),
        ]
        return {key: str(value) for key, value in pairs if value is not None}


# --------------------------------------------------------------------------- #
# Builder — построение меток                                                  #
# --------------------------------------------------------------------------- #


def build_run_tags(
    *,
    doc_id: str | None = None,
    source_id: str | None = None,
    ingest_job_id: str | None = None,
    run_type: str = DEFAULT_RUN_TYPE,
    partition_key: str | None = None,
    schedule_name: str | None = None,
) -> dict[str, str]:
    """Build a namespaced ``dict[str, str]`` of run tags — построить метки прогона.

    Keys are emitted under the ``kg/*`` and ``dagster/*`` namespaces. Fields left as
    ``None`` are omitted; every emitted value is string-coerced. ``run_type`` always
    appears and defaults to ``"manual"``.
    """
    return RunTags(
        run_type=run_type,
        doc_id=doc_id,
        source_id=source_id,
        ingest_job_id=ingest_job_id,
        partition_key=partition_key,
        schedule_name=schedule_name,
    ).as_dict()


# --------------------------------------------------------------------------- #
# Matching & filtering — сопоставление и фильтрация                           #
# --------------------------------------------------------------------------- #


def matches_tags(run_tags: Mapping[str, str], query: Mapping[str, str]) -> bool:
    """Return ``True`` iff every ``query`` pair is present and equal — совпадение.

    An empty ``query`` matches any run (there is nothing to violate).
    """
    return all(run_tags.get(key) == value for key, value in query.items())


def filter_runs(
    runs: Sequence[Mapping[str, str]], query: Mapping[str, str]
) -> list[Mapping[str, str]]:
    """Keep only runs whose tags satisfy ``query`` — отфильтровать прогоны.

    Order is preserved; each kept element is the original run mapping.
    """
    return [run for run in runs if matches_tags(run, query)]
