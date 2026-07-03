"""Защита проверенных полей от перезаписи — verified-field upsert guard (§16.8).

When an automated pipeline re-upserts a node, human-verified properties must not be
silently clobbered by fresh (possibly worse) machine-extracted values. This guard is
the storage-layer equivalent of Cypher's ``apoc.map.removeKeys(incoming, verified)``:
given the ``incoming`` property map, the list of ``verified_fields`` and the node's
``current`` stored props, it splits the incoming map into the props that should
actually be SET and the verified props that must be preserved (skipped).

Поведение / behaviour:

* Fields NOT in ``verified_fields`` always land in ``applied`` (they get written).
* Verified fields are never written — they go into ``skipped``.
* A verified field whose ``incoming`` value differs from the ``current`` stored value
  (including the case where the field is absent from ``current`` — the incoming write
  would *introduce* a value) is additionally recorded in ``conflicts``: a signal that a
  human-verified fact disagrees with the machine, i.e. a candidate review task
  (задача на ревью). A verified field whose incoming value equals the current value is
  a harmless no-op — skipped but not a conflict.

The guard is pure and backend-agnostic; callers feed ``applied`` to their own SET and
raise a review task when :func:`needs_review_task` is true.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

_SENTINEL = object()


@dataclass(frozen=True)
class GuardResult:
    """Outcome of splitting an incoming upsert against verified fields (§16.8).

    :param applied: props to actually SET (non-verified incoming fields).
    :param skipped: verified fields present in ``incoming`` that were preserved.
    :param conflicts: verified fields whose incoming value differs from ``current``.
    """

    applied: dict[str, Any] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view — сериализуемое представление результата."""
        return asdict(self)


def filter_upsert(
    incoming: Mapping[str, Any],
    verified_fields: Sequence[str],
    current: Mapping[str, Any],
) -> GuardResult:
    """Split ``incoming`` into writable vs. preserved verified props (§16.8).

    Fields not in ``verified_fields`` are collected into ``applied``; verified fields
    present in ``incoming`` go into ``skipped``, and are additionally flagged as a
    ``conflict`` when their incoming value differs from ``current`` (absence in
    ``current`` counts as a differing, i.e. introducing, value).
    """
    verified = set(verified_fields)
    applied: dict[str, Any] = {}
    skipped: list[str] = []
    conflicts: list[str] = []

    for key, value in incoming.items():
        if key not in verified:
            applied[key] = value
            continue
        skipped.append(key)
        if current.get(key, _SENTINEL) != value:
            conflicts.append(key)

    return GuardResult(applied=applied, skipped=skipped, conflicts=conflicts)


def needs_review_task(result: GuardResult) -> bool:
    """True when a verified field conflicts — требуется задача на ревью (§16.8)."""
    return len(result.conflicts) > 0
