"""Gap lifecycle — resolve / reopen / auto-resolve over the graph (§15.2).

A :class:`~kg_retrievers.gap_analysis.GapScanner` *materialises* Gap nodes; this
module drives their **lifecycle** afterwards — closing a gap when a curator (or the
graph itself) shows it is no longer missing, and reopening it if that turns out to
be premature. Жизненный цикл пропуска: open → resolved → (reopen) → open.

A fresh Gap has no ``status`` prop and is treated as ``open``. Resolving stamps the
кто/когда/почему onto the node:

    status            = "resolved"
    resolved_at       = <when it was closed>
    resolution_reason = <why>
    resolved_by       = <who>

Kuzu note: none of ``status`` / ``resolved_at`` / ``resolution_reason`` /
``resolved_by`` are typed :data:`~kg_retrievers.graph_store.NODE_COLUMNS`, so they
live in the JSON ``props`` catch-all — **not** queryable columns. We therefore
RETURN base columns from Cypher and read the lifecycle flags back through
:meth:`KuzuGraphStore.get_node`, which flattens ``props`` for us. Writes go through
:meth:`KuzuGraphStore.upsert_node` (a MERGE that preserves the ``id``), re-writing
the full prop set so nothing else on the node is lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.enums import GapType

_log = get_logger("gap_lifecycle")

GAP_LABEL = "Gap"
STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
AUTO_ACTOR = "auto"

# The gap type this module can close automatically (§15.2): a missing property
# value is *covered* once a Measurement of that property exists about the subject.
MISSING_PROPERTY = str(GapType.MISSING_PROPERTY_VALUE)

# Relationship types linking a Gap / Measurement to the subject it is *about*
# (пропуск/наблюдение → материал/режим). Matched by type for robustness.
ABOUT_TYPES = ("ABOUT", "ABOUT_MATERIAL", "ABOUT_REGIME")

# Prop keys that carry the resolution stamp; cleared on reopen (status is reset
# to STATUS_OPEN separately so the JSON ``props`` column is always rewritten).
_RESOLUTION_KEYS = ("resolved_at", "resolution_reason", "resolved_by")


@dataclass(frozen=True)
class GapResolution:
    """Record of a single gap closure — кто/когда/почему (§15.2).

    ``gap_id`` is the closed Gap; ``actor`` is who closed it (``resolved_by``);
    ``resolved_at`` is when; ``reason`` is why (``resolution_reason``); ``status``
    is the resulting lifecycle state (always :data:`STATUS_RESOLVED`).
    """

    gap_id: str
    status: str
    reason: str
    actor: str
    resolved_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "status": self.status,
            "reason": self.reason,
            "actor": self.actor,
            "resolved_at": self.resolved_at,
        }


def _preserved_props(node: dict[str, Any]) -> dict[str, Any]:
    """All of a node's fields except ``id``/``label`` (the MERGE-owned parts).

    :meth:`KuzuGraphStore.get_node` flattens the JSON ``props`` catch-all into the
    top level, so re-passing these to ``upsert_node`` round-trips every column and
    prop without loss (``id`` is the primary key, ``label`` is positional).
    """
    return {k: v for k, v in node.items() if k not in ("id", "label")}


def resolve_gap(
    store: KuzuGraphStore,
    gap_id: str,
    *,
    reason: str,
    actor: str,
    at: str | None = None,
) -> GapResolution | None:
    """Close a gap — stamp it ``resolved`` with the кто/когда/почему (§15.2).

    Sets ``status='resolved'`` plus ``resolved_at`` (defaults to now, UTC ISO),
    ``resolution_reason=reason`` and ``resolved_by=actor`` on the Gap node via
    :meth:`KuzuGraphStore.upsert_node`, which re-writes the full prop set so no
    other field on the node is lost. These flags live in the JSON ``props``
    catch-all and are read back through :meth:`KuzuGraphStore.get_node`. Returns
    the :class:`GapResolution` record, or ``None`` (a graceful no-op) when
    ``gap_id`` is unknown.
    """
    node = store.get_node(gap_id)
    if node is None:
        _log.warning("resolve_gap.unknown", gap_id=gap_id)
        return None
    when = at or datetime.now(UTC).isoformat()
    props = _preserved_props(node)
    props["status"] = STATUS_RESOLVED
    props["resolved_at"] = when
    props["resolution_reason"] = reason
    props["resolved_by"] = actor
    store.upsert_node(gap_id, node.get("label", GAP_LABEL), **props)
    _log.info("resolve_gap.done", gap_id=gap_id, actor=actor, at=when)
    return GapResolution(
        gap_id=gap_id, status=STATUS_RESOLVED, reason=reason, actor=actor, resolved_at=when
    )


def reopen_gap(store: KuzuGraphStore, gap_id: str) -> bool:
    """Reopen a previously-resolved gap — снова открыть пропуск (§15.2).

    Clears the resolution stamp (``resolved_at`` and its кто/почему metadata) and
    resets ``status='open'``, re-writing the node via
    :meth:`KuzuGraphStore.upsert_node`. Setting ``status`` (a non-column prop)
    guarantees the JSON ``props`` column is re-persisted, so the stale stamp is
    dropped. Returns ``True`` when a gap was reopened, ``False`` when ``gap_id`` is
    unknown (graceful no-op).
    """
    node = store.get_node(gap_id)
    if node is None:
        _log.warning("reopen_gap.unknown", gap_id=gap_id)
        return False
    props = {k: v for k, v in _preserved_props(node).items() if k not in _RESOLUTION_KEYS}
    props["status"] = STATUS_OPEN
    store.upsert_node(gap_id, node.get("label", GAP_LABEL), **props)
    _log.info("reopen_gap.done", gap_id=gap_id)
    return True


def gap_status(store: KuzuGraphStore, gap_id: str) -> str | None:
    """Current lifecycle state of a gap — ``open`` / ``resolved`` (§15.2).

    Reads ``status`` back through :meth:`KuzuGraphStore.get_node` (it lives in the
    JSON ``props`` catch-all, not a queryable column). A gap that has never been
    resolved carries no ``status`` prop and defaults to :data:`STATUS_OPEN`.
    Unknown ids yield ``None``.
    """
    node = store.get_node(gap_id)
    if node is None:
        return None
    return str(node.get("status", STATUS_OPEN))


def _subjects_of_gap(store: KuzuGraphStore, gap_id: str) -> list[str]:
    """Ids of the subjects a Gap is *about* — walk ``Gap-[ABOUT]->subject``."""
    rows = store.rows(
        "MATCH (g:Node {id:$gid})-[r:Rel]->(s:Node) WHERE r.type IN $about RETURN DISTINCT s.id",
        {"gid": gap_id, "about": list(ABOUT_TYPES)},
    )
    return [r[0] for r in rows]


def _subject_has_measurement(
    store: KuzuGraphStore, subject_id: str, property_name: str | None
) -> bool:
    """True iff a Measurement is attached to ``subject_id`` (§15.2).

    When ``property_name`` is given, the Measurement's ``property_name`` must match
    (свойство того же типа); when it is ``None`` any Measurement about the subject
    counts. Measurement→subject links are matched undirected across the
    :data:`ABOUT_TYPES` family.
    """
    rows = store.rows(
        "MATCH (m:Node)-[r:Rel]-(s:Node {id:$sid}) "
        "WHERE m.label='Measurement' AND r.type IN $about "
        "RETURN DISTINCT m.id, coalesce(m.property_name,'')",
        {"sid": subject_id, "about": list(ABOUT_TYPES)},
    )
    return any(not property_name or pname == property_name for _mid, pname in rows)


def _auto_reason(property_name: str | None) -> str:
    """Human-readable reason string for an automatic closure (RU/EN)."""
    if property_name:
        return f"Автозакрытие: найдено измерение свойства «{property_name}» (auto-resolved)"
    return "Автозакрытие: найдено измерение по объекту (auto-resolved)"


def auto_resolve_if_covered(
    store: KuzuGraphStore,
    gap_id: str,
    *,
    actor: str = AUTO_ACTOR,
    at: str | None = None,
) -> GapResolution | None:
    """Auto-close a ``missing_property`` gap once the graph covers it (§15.2).

    Walks ``Gap-[ABOUT]->subject`` and resolves the gap when the subject now has a
    Measurement of that property (свойство теперь измерено). A no-op (returns
    ``None``) when: the gap is unknown, it is not a
    :data:`~kg_schema.enums.GapType.MISSING_PROPERTY_VALUE` gap, it is already
    resolved (idempotent), or no covering Measurement exists yet. On success it
    delegates to :func:`resolve_gap` and returns the :class:`GapResolution`.
    """
    node = store.get_node(gap_id)
    if node is None:
        return None
    if node.get("gap_type") != MISSING_PROPERTY:
        return None
    if node.get("status") == STATUS_RESOLVED:
        return None
    prop = node.get("property_name")
    for subject_id in _subjects_of_gap(store, gap_id):
        if _subject_has_measurement(store, subject_id, prop):
            return resolve_gap(store, gap_id, reason=_auto_reason(prop), actor=actor, at=at)
    return None
