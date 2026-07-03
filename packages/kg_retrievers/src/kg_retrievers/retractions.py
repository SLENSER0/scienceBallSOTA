"""Soft-retraction of observations and ``include_retracted`` semantics (§25.12).

A *retraction* (ретракция) withdraws an observation — a ``Measurement`` or a
``Claim`` — **without deleting it**. The node stays in the graph so provenance,
audit and the absence-layer can still see it; it is merely flagged inactive:

    retracted = True
    valid_to  = <when it stopped being an active fact>
    retraction_reason = <why>
    retracted_by = <who>

This soft model is what §25.12 requires: retracted data is *classified
separately* — it is neither a настоящий gap (genuine_gap) nor a пропуск
извлечения (possible_miss) — and it must **not** be mixed into ordinary
analytics, ranking or recommendation as an active fact. Only callers that opt in
with ``include_retracted=True`` (the absence-layer) get to see it; every legacy
query path keeps its old behaviour (retracted observations hidden).

Kuzu note: ``retracted`` / ``valid_to`` / ``retraction_reason`` / ``retracted_by``
are **not** typed :data:`~kg_retrievers.graph_store.NODE_COLUMNS`, so they live in
the JSON ``props`` catch-all — not queryable columns. We therefore RETURN base
columns from Cypher and read the retraction flags back through
:meth:`KuzuGraphStore.get_node`, which flattens ``props`` for us. Writes go
through :meth:`KuzuGraphStore.upsert_node` (a MERGE that preserves the ``id``),
re-writing the full prop set so nothing else on the node is lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("retractions")

# Node labels that count as *observations* eligible for retraction (§25.12).
OBSERVATION_LABELS = ("Measurement", "Claim")

# Relationship types that attach an observation to the subject it is *about*
# (наблюдение → материал/режим). Matched undirected for robustness.
ABOUT_TYPES = ("ABOUT_MATERIAL", "ABOUT_REGIME", "ABOUT")

# Prop keys that carry the soft-retraction tombstone; cleared on unretract.
_RETRACTION_KEYS = ("retracted", "valid_to", "retraction_reason", "retracted_by")


@dataclass(frozen=True)
class Retraction:
    """Metadata of a single soft-retraction — кто/когда/почему (§25.12).

    ``node_id`` is the retracted observation; ``actor`` is who withdrew it
    (``retracted_by``); ``at`` is when it stopped being an active fact
    (``valid_to``); ``reason`` is why (``retraction_reason``).
    """

    node_id: str
    reason: str
    actor: str
    at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "reason": self.reason,
            "actor": self.actor,
            "at": self.at,
        }


def _is_retracted_node(node: dict[str, Any] | None) -> bool:
    """True when a flattened node dict carries an active retraction flag."""
    return bool(node and node.get("retracted") is True)


def _preserved_props(node: dict[str, Any]) -> dict[str, Any]:
    """All of a node's fields except ``id``/``label`` (the MERGE-owned parts).

    :meth:`KuzuGraphStore.get_node` flattens the JSON ``props`` catch-all into the
    top level, so re-passing these to ``upsert_node`` round-trips every column and
    prop without loss (``id`` is the primary key, ``label`` is positional).
    """
    return {k: v for k, v in node.items() if k not in ("id", "label")}


def retract(
    store: KuzuGraphStore,
    node_id: str,
    *,
    reason: str,
    actor: str,
    at: str,
) -> Retraction | None:
    """Soft-retract an observation — flag it inactive, never delete it (§25.12).

    Sets ``retracted=True`` plus the кто/когда/почему metadata
    (``retracted_by=actor``, ``valid_to=at``, ``retraction_reason=reason``) on the
    ``Measurement`` / ``Claim`` node via :meth:`KuzuGraphStore.upsert_node`, which
    re-writes the full prop set so no other field on the node is lost. Returns the
    :class:`Retraction` record, or ``None`` (a graceful no-op) when ``node_id`` is
    unknown.
    """
    node = store.get_node(node_id)
    if node is None:
        _log.warning("retract.unknown_node", node_id=node_id)
        return None
    props = _preserved_props(node)
    props["retracted"] = True
    props["valid_to"] = at
    props["retraction_reason"] = reason
    props["retracted_by"] = actor
    store.upsert_node(node_id, node.get("label", "Measurement"), **props)
    _log.info("retract.done", node_id=node_id, actor=actor, at=at)
    return Retraction(node_id=node_id, reason=reason, actor=actor, at=at)


def unretract(store: KuzuGraphStore, node_id: str) -> bool:
    """Restore a soft-retracted observation to active (§25.12).

    Clears the retraction tombstone (``retracted`` and its кто/когда/почему
    metadata) and re-writes the node via :meth:`KuzuGraphStore.upsert_node`,
    leaving an explicit ``retracted=False`` marker so ``props`` is always
    re-persisted. Returns ``True`` when a node was restored, ``False`` when
    ``node_id`` is unknown (graceful no-op).
    """
    node = store.get_node(node_id)
    if node is None:
        _log.warning("unretract.unknown_node", node_id=node_id)
        return False
    props = {k: v for k, v in _preserved_props(node).items() if k not in _RETRACTION_KEYS}
    # Keep an explicit False marker so the JSON props column is always rewritten
    # (an empty extra dict would otherwise leave the stale tombstone in place).
    props["retracted"] = False
    store.upsert_node(node_id, node.get("label", "Measurement"), **props)
    _log.info("unretract.done", node_id=node_id)
    return True


def is_retracted(store: KuzuGraphStore, node_id: str) -> bool:
    """True iff ``node_id`` is an actively soft-retracted observation (§25.12).

    Reads the flag back through :meth:`KuzuGraphStore.get_node` (it lives in the
    JSON ``props`` catch-all, not a queryable column). Unknown ids yield ``False``.
    """
    return _is_retracted_node(store.get_node(node_id))


def active_measurements(
    store: KuzuGraphStore,
    subject_id: str,
    *,
    include_retracted: bool = False,
) -> list[dict[str, Any]]:
    """Observations about a subject, filtered by retraction state (§25.12).

    Returns the ``Measurement`` / ``Claim`` nodes attached to ``subject_id`` via an
    ``ABOUT_*`` relationship, as flattened node dicts sorted by id. By default
    (``include_retracted=False``) soft-retracted observations are hidden — the
    legacy semantics every ordinary analytics/ranking path relies on. Pass
    ``include_retracted=True`` (the absence-layer) to get both active and retracted
    observations. Unknown / unattached subjects yield ``[]``.
    """
    rows = store.rows(
        "MATCH (m:Node)-[r:Rel]-(s:Node {id:$sid}) "
        "WHERE m.label IN $labels AND r.type IN $about "
        "RETURN DISTINCT m.id ORDER BY m.id",
        {"sid": subject_id, "labels": list(OBSERVATION_LABELS), "about": list(ABOUT_TYPES)},
    )
    out: list[dict[str, Any]] = []
    for (mid,) in rows:
        node = store.get_node(mid)
        if node is None:
            continue
        if not include_retracted and _is_retracted_node(node):
            continue
        out.append(node)
    _log.info(
        "active_measurements.done",
        subject_id=subject_id,
        n=len(out),
        include_retracted=include_retracted,
    )
    return out
