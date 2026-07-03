"""Orphan-node detection over the entity graph (§8.16 graph hygiene).

Изолированные узлы / isolated nodes — nodes that carry no relationship in either
direction. They are a data-quality smell: an entity that was extracted but never
linked to any observation, document, or peer usually points at a broken
extraction or a dangling reference.

This module reads a :class:`KuzuGraphStore` (never writes) and answers two
questions:

- ``find_orphans`` — list the ids of nodes with degree 0 (optionally restricted
  to a set of labels);
- ``orphan_report`` — a frozen :class:`OrphanReport` (with ``as_dict``) giving
  the total orphan count and a per-label breakdown.

Kuzu note: custom node props are not queryable columns, so we RETURN only the
base ``id`` / ``label`` columns here; anything else would be read via
``store.get_node``. Orphans are found by subtracting the set of edge endpoints
from the set of all node ids — reliable on empty and disconnected graphs alike.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from kg_retrievers.graph_store import KuzuGraphStore

_ALL_NODES = "MATCH (n:Node) RETURN n.id, n.label"
_ALL_ENDPOINTS = "MATCH (a:Node)-[:Rel]->(b:Node) RETURN a.id, b.id"


def _connected_ids(store: KuzuGraphStore) -> set[str]:
    """Ids of every node that is an endpoint of at least one edge."""
    connected: set[str] = set()
    for src, dst in store.rows(_ALL_ENDPOINTS):
        connected.add(src)
        connected.add(dst)
    return connected


def find_orphans(store: KuzuGraphStore, *, labels: set[str] | None = None) -> list[str]:
    """Return the ids of nodes with no edges (§8.16), sorted for determinism.

    ``labels`` — если задан, учитываются только узлы с этими метками / when given,
    only nodes carrying one of these labels are considered.
    """
    connected = _connected_ids(store)
    label_filter = set(labels) if labels is not None else None
    orphans = [
        nid
        for nid, label in store.rows(_ALL_NODES)
        if nid not in connected and (label_filter is None or label in label_filter)
    ]
    return sorted(orphans)


@dataclass(frozen=True)
class OrphanReport:
    """Summary of orphan nodes in a graph (§8.16).

    ``total_orphans`` — общее число изолированных узлов / total isolated nodes;
    ``by_label`` — их распределение по меткам / their per-label breakdown.
    """

    total_orphans: int
    by_label: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"total_orphans": self.total_orphans, "by_label": dict(self.by_label)}


def orphan_report(store: KuzuGraphStore) -> OrphanReport:
    """Build an :class:`OrphanReport` over every orphan node in ``store`` (§8.16)."""
    connected = _connected_ids(store)
    counts: Counter[str] = Counter()
    for nid, label in store.rows(_ALL_NODES):
        if nid not in connected:
            counts[label or ""] += 1
    by_label = dict(sorted(counts.items()))
    return OrphanReport(total_orphans=sum(counts.values()), by_label=by_label)
