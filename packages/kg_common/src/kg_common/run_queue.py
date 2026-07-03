"""Queued-run admission coordinator — координатор допуска запусков (§9.7).

A run queue holds pipeline runs waiting for a launch slot. The coordinator
decides, deterministically and without side effects, which queued runs may
start *right now* given two kinds of limits:

* ``max_concurrent`` — a global ceiling on runs in flight («глобальный
  потолок одновременных запусков»), counting both already-running runs and
  the ones admitted in this decision.
* ``tag_limits``     — per-tag ceilings keyed by a ``(key, value)`` pair, e.g.
  ``{("engine", "llm"): 1}`` allows at most one running run tagged
  ``engine=llm``. A tag with no entry is unlimited.

Admission is strictly FIFO over the queue («первым пришёл — первым допущен»):
we walk the queue in order and launch a run only if launching it keeps every
applicable limit satisfied; otherwise the run is held. Holding one run never
blocks a *later* run from launching — each run is judged on its own tags — so
a run whose tags carry no limit is unaffected by other tags' limits.

Everything here is pure: no I/O, no wall-clock, no globals mutated at call
time. Records are frozen dataclasses, so callers cannot mutate a decision.

Public API:

* :class:`QueuedRun`        — frozen ``{run_id, tags}`` record with ``as_dict``.
* :class:`AdmissionDecision`— frozen ``{launch, hold}`` record with ``as_dict``.
* :func:`admit`             — FIFO admission under global + per-tag limits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

__all__ = [
    "QueuedRun",
    "AdmissionDecision",
    "admit",
]


# --------------------------------------------------------------------------- #
# Records — записи                                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class QueuedRun:
    """A run waiting in the queue — запуск в очереди.

    ``tags`` maps a tag key to its value, e.g. ``{"engine": "llm"}``. It is
    stored as an immutable :class:`~types.MappingProxyType` so the frozen
    record cannot be mutated through the mapping.
    """

    run_id: str
    tags: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        # Freeze the tag mapping — заморозить отображение тегов.
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))

    def as_dict(self) -> dict[str, object]:
        """Plain-``dict`` view — представление в виде словаря."""
        return {"run_id": self.run_id, "tags": dict(self.tags)}


@dataclass(frozen=True)
class AdmissionDecision:
    """Result of an admission pass — результат прохода допуска.

    ``launch`` is the ordered tuple of run ids admitted to start now; ``hold``
    is the ordered tuple of run ids kept in the queue. Together they contain
    every input run id exactly once, preserving queue order within each.
    """

    launch: tuple[str, ...] = ()
    hold: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, list[str]]:
        """Plain-``dict`` view — представление в виде словаря."""
        return {"launch": list(self.launch), "hold": list(self.hold)}


# --------------------------------------------------------------------------- #
# Admission — допуск                                                           #
# --------------------------------------------------------------------------- #


def admit(
    queued: Sequence[QueuedRun],
    *,
    in_flight: Sequence[Mapping[str, str]] = (),
    max_concurrent: int,
    tag_limits: Mapping[tuple[str, str], int] = MappingProxyType({}),
) -> AdmissionDecision:
    """Decide which queued runs may launch now — решить, кого допустить.

    FIFO over ``queued``: launch a run while the global running count
    (already ``in_flight`` plus launched so far) is below ``max_concurrent``
    **and**, for every tag ``(k, v)`` the run carries, the running+launched
    count with that tag is below ``tag_limits[(k, v)]`` (unlimited if absent).
    Otherwise the run is held. Holding a run does not block later runs.

    :param queued: runs awaiting a slot, in FIFO order.
    :param in_flight: tag mappings of runs already running (не в очереди).
    :param max_concurrent: global ceiling on running runs.
    :param tag_limits: per-``(key, value)`` ceilings; missing ⇒ unlimited.
    :returns: an :class:`AdmissionDecision` partitioning ``queued`` run ids.
    """
    # Running totals seeded from in-flight runs — счётчики от текущих запусков.
    running = len(in_flight)
    tag_counts: dict[tuple[str, str], int] = {}
    for tags in in_flight:
        for key, value in tags.items():
            tag_counts[(key, value)] = tag_counts.get((key, value), 0) + 1

    launch: list[str] = []
    hold: list[str] = []

    for run in queued:
        pairs = tuple(run.tags.items())
        # Global ceiling — глобальный потолок.
        fits_global = running < max_concurrent
        # Per-tag ceilings — потолки по тегам.
        fits_tags = all(
            (key, value) not in tag_limits
            or tag_counts.get((key, value), 0) < tag_limits[(key, value)]
            for key, value in pairs
        )
        if fits_global and fits_tags:
            launch.append(run.run_id)
            running += 1
            for key, value in pairs:
                tag_counts[(key, value)] = tag_counts.get((key, value), 0) + 1
        else:
            hold.append(run.run_id)

    return AdmissionDecision(launch=tuple(launch), hold=tuple(hold))
