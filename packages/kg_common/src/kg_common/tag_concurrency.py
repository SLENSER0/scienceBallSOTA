"""Per-tag run concurrency limits — потеговые лимиты параллелизма (§9.7).

Dagster lets you cap how many runs may execute *simultaneously* while sharing a
given tag key/value — e.g. to protect a fragile Neo4j writer or a rate-limited
LLM endpoint from being hammered by too many concurrent runs. This is
independent of the run-queue's single *global* cap: a global limit of 20 may
still coexist with «at most one ``llm=true`` run at a time».

This module models that admission decision as pure functions of the in-flight
run tags and the configured limits — no scheduler, no store, no side effects.

* :class:`TagLimit` — a frozen rule ``(key, value, limit)``. A concrete
  ``value`` limits runs carrying *that exact* key/value pair; ``value is None``
  means «per distinct value» — the limit applies independently to each observed
  value of ``key`` (so ``pool=a`` and ``pool=b`` never crowd each other out).
* :func:`slots_used` — how many in-flight runs a limit currently counts.
* :func:`can_admit` — may a candidate run start now, and if not, which limit
  keys does it violate.

Public API:

* :class:`TagLimit` — frozen rule with :meth:`TagLimit.as_dict`.
* :func:`slots_used` — count matching in-flight runs.
* :func:`can_admit` — admission gate returning ``(ok, violated_keys)``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "TagLimit",
    "slots_used",
    "can_admit",
]


@dataclass(frozen=True, slots=True)
class TagLimit:
    """Immutable per-tag concurrency rule — лимит по тегу (§9.7).

    ``value is None`` means the limit is enforced *per distinct value* of
    ``key``; a concrete ``value`` targets only the exact ``key=value`` pair.
    """

    key: str
    value: str | None
    limit: int

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("key must be non-empty — ключ не должен быть пустым")
        if self.limit < 0:
            raise ValueError("limit must be >= 0 — лимит не может быть отрицательным")

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — правило как словарь (§9.7)."""
        return {"key": self.key, "value": self.value, "limit": self.limit}


def slots_used(in_flight: Sequence[Mapping[str, str]], limit: TagLimit) -> int:
    """Count in-flight runs the ``limit`` matches — занятые слоты (§9.7).

    For a value-specific limit this counts runs whose tag equals
    ``limit.value``. For a ``value is None`` limit there is no single count —
    each distinct value has its own pool — so we return the size of the *largest*
    such pool, i.e. the busiest value's occupancy.
    """
    if limit.value is not None:
        return sum(1 for tags in in_flight if tags.get(limit.key) == limit.value)
    counts: dict[str, int] = {}
    for tags in in_flight:
        val = tags.get(limit.key)
        if val is not None:
            counts[val] = counts.get(val, 0) + 1
    return max(counts.values(), default=0)


def can_admit(
    candidate_tags: Mapping[str, str],
    in_flight: Sequence[Mapping[str, str]],
    limits: Sequence[TagLimit],
) -> tuple[bool, tuple[str, ...]]:
    """May the candidate run start now? — можно ли запустить? (§9.7).

    Returns ``(ok, violated_keys)``. A limit is only relevant if the candidate
    itself carries the tag being limited (a run without the tag is never gated
    by it). For a value-specific limit the candidate must also match the exact
    value; for a ``value is None`` limit we count only runs sharing the
    candidate's *own* value of that key. Admission fails when adding the
    candidate would exceed the limit; every violated limit key is reported.
    """
    violated: list[str] = []
    for limit in limits:
        cand_val = candidate_tags.get(limit.key)
        if cand_val is None:
            continue  # Candidate lacks the tag — this limit does not apply.
        if limit.value is not None and cand_val != limit.value:
            continue  # Candidate's value is outside this value-specific limit.
        # Count in-flight runs sharing the candidate's value of this key.
        used = sum(1 for tags in in_flight if tags.get(limit.key) == cand_val)
        if used + 1 > limit.limit:
            violated.append(limit.key)
    return (not violated, tuple(violated))
