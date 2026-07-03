"""Sensor RunRequest + run_key dedup — заявки на запуск сенсора (§9.6).

A Dagster *sensor* (see :mod:`kg_common.sensor_cursor` for the watermark side)
turns freshly-observed tokens into **run requests**. Each request carries a
``run_key`` that Dagster uses for **idempotency** («идемпотентность»): if a run
with a given ``run_key`` has already been launched, re-emitting the same key is a
no-op. So a sensor may safely re-poll an overlapping window and re-emit the same
requests — only genuinely new keys start work.

This module models that emission as small frozen values plus pure functions. No
wall-clock, no I/O, no Dagster import — a scheduler can drive it however it likes.

Public API:

* :class:`RunRequest` — frozen ``(run_key, job_name, partition_key, tags)``
  record with :meth:`RunRequest.as_dict`.
* :func:`build_run_requests` — one :class:`RunRequest` per new key, skipping keys
  already requested and deduping repeats within the input, in input order.
* :func:`dedup_keys` — unique ``run_key`` values from a request sequence, in
  order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from types import MappingProxyType

__all__ = [
    "RunRequest",
    "build_run_requests",
    "dedup_keys",
]

_EMPTY_TAGS: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Immutable sensor run request — заявка на запуск (§9.6).

    ``run_key`` is the idempotency token: Dagster launches at most one run per
    distinct ``run_key`` («ключ идемпотентности»). ``job_name`` names the job to
    launch; ``partition_key`` optionally targets a partition; ``tags`` is an
    immutable string→string mapping attached to the run. Both ``run_key`` and
    ``job_name`` must be non-empty.
    """

    run_key: str
    job_name: str
    partition_key: str | None = None
    tags: Mapping[str, str] = field(default_factory=lambda: _EMPTY_TAGS)

    def __post_init__(self) -> None:
        """Validate required fields — проверка обязательных полей (§9.6)."""
        if not self.run_key:
            raise ValueError("run_key must be non-empty — пустой run_key")
        if not self.job_name:
            raise ValueError("job_name must be non-empty — пустой job_name")

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — сериализация заявки (§9.6)."""
        return {
            "run_key": self.run_key,
            "job_name": self.job_name,
            "partition_key": self.partition_key,
            "tags": dict(self.tags),
        }


def build_run_requests(
    job_name: str,
    new_keys: Sequence[str],
    *,
    already_requested: Set[str] = frozenset(),
    tag_fn: Callable[[str], Mapping[str, str]] | None = None,
) -> tuple[RunRequest, ...]:
    """Build one request per new key — построить заявки (§9.6).

    Iterates ``new_keys`` **in input order**, using each key as both ``run_key``
    and ``partition_key``. A key is skipped when it is in ``already_requested``
    (already launched — «уже запущено») or when it has already been emitted
    earlier in this call (dedup of repeats within the input). When ``tag_fn`` is
    given, its result for the key is attached as :attr:`RunRequest.tags`.
    """
    requests: list[RunRequest] = []
    emitted: set[str] = set()
    for key in new_keys:
        if key in already_requested or key in emitted:
            continue
        emitted.add(key)
        tags = _EMPTY_TAGS if tag_fn is None else MappingProxyType(dict(tag_fn(key)))
        requests.append(
            RunRequest(
                run_key=key,
                job_name=job_name,
                partition_key=key,
                tags=tags,
            )
        )
    return tuple(requests)


def dedup_keys(run_requests: Sequence[RunRequest]) -> tuple[str, ...]:
    """Unique ``run_key`` values in order — уникальные ключи (§9.6).

    Returns each distinct ``run_key`` the first time it appears, preserving the
    order of ``run_requests``.
    """
    seen: set[str] = set()
    keys: list[str] = []
    for request in run_requests:
        if request.run_key in seen:
            continue
        seen.add(request.run_key)
        keys.append(request.run_key)
    return tuple(keys)
