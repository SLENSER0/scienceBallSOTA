"""Deterministic Qdrant point-id planning for GraphRAG community reports (§11.5).

A GraphRAG build produces one community report per (community, level). To upsert
these into a Qdrant collection idempotently we need a *stable, deterministic*
point id per report — re-running a build must reuse the same ids so a second
upsert is a no-op rather than a duplicate.

Идемпотентность (idempotency) is the whole point: :func:`point_id` derives a
sha256-based hex id from the ``(build_id, community_id, level)`` tuple, and
:func:`plan_upsert` splits reports into those not yet present (``to_upsert``) and
those already stored (``skipped``). Feeding the produced ids back as
``existing_ids`` yields an empty ``to_upsert`` — a proven no-op second run.

This module is pure: it computes ids and set membership only. It never touches
Qdrant or the network.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Field separator for the id-material string. A control char that cannot appear
# in an id keeps ("a|", "b") distinct from ("a", "|b") — no ambiguous joins.
_SEP = "\x1f"


def point_id(build_id: str, community_id: str, level: int) -> str:
    """Deterministic sha256 hex id for a ``(build_id, community_id, level)`` tuple.

    Стабильный (stable): identical arguments always yield the same 64-char hex
    digest, and any change to ``build_id``, ``community_id`` or ``level`` (e.g. a
    different community level) yields a different id. The three fields are joined
    with an unambiguous separator before hashing so distinct tuples cannot alias.
    """
    material = _SEP.join((build_id, community_id, str(level)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UpsertPlan:
    """Split of community reports into new vs already-present point ids (§11.5).

    ``to_upsert`` holds the point ids not found in ``existing_ids`` (order of first
    appearance, de-duplicated); ``skipped`` holds ids already present. ``total`` is
    the number of input reports (before de-duplication), so it can exceed
    ``len(to_upsert) + len(skipped)`` when reports collapse to one id.
    """

    to_upsert: list[str]
    skipped: list[str]
    total: int

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{to_upsert, skipped, total}`` (id lists are hex strings)."""
        return {
            "to_upsert": list(self.to_upsert),
            "skipped": list(self.skipped),
            "total": self.total,
        }


def plan_upsert(
    build_id: str,
    reports: list[dict],
    existing_ids: set[str],
) -> UpsertPlan:
    """Plan an idempotent Qdrant upsert of community reports (§11.5).

    Each report must carry ``community_id`` and ``level``; its point id is
    :func:`point_id`. Ids already in ``existing_ids`` go to ``skipped``; the rest go
    to ``to_upsert``. De-duplication is by point id — two reports with the same
    ``(build_id, community_id, level)`` collapse to a single id, listed once. Within
    a single call, once an id is queued for upsert a later duplicate is not queued
    again. ``total`` counts input reports.
    """
    to_upsert: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for report in reports:
        pid = point_id(build_id, str(report["community_id"]), int(report["level"]))
        if pid in seen:
            continue
        seen.add(pid)
        if pid in existing_ids:
            skipped.append(pid)
        else:
            to_upsert.append(pid)
    return UpsertPlan(to_upsert=to_upsert, skipped=skipped, total=len(reports))
