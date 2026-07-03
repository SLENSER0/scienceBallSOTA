"""GraphRAG community-view graph payload (§11.8 / §5.3).

Строит компактный граф-обзор (community view — обзор кластеров знаний) для UI:
one node per использованное community (кластер), a handful of its member entities
(сущности-участники), and the community hierarchy edges (иерархия подкластеров).
The payload is Reagraph-shaped (``{'nodes': [...], 'edges': [...]}``) so the frontend
graph widget can render it directly.

Node ``type`` is one of ``{'community', 'report', 'entity'}`` and edge ``type`` is one
of ``{'HAS_SUBCOMMUNITY', 'HAS_REPORT', 'INCLUDES_ENTITY'}`` (§5.3 graph schema).
Everything is deterministic and offline-safe: node ids are stable (``f'community:{cid}'``,
``f'entity:{eid}'``), member entities are read from an embedded KuzuGraphStore and sorted,
and hierarchy edges come from a caller-supplied ``subcommunities`` mapping — no clock,
no LLM.

Kuzu note: ``id``/``label``/``name`` are base columns and safe to RETURN directly; any
other property would have to be read via :meth:`KuzuGraphStore.get_node`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import NodeLabel

_log = get_logger("community_view_payload")

# Node types (§5.3) — тип узла обзора.
NODE_TYPES: frozenset[str] = frozenset({"community", "report", "entity"})
# Edge types (§5.3) — тип ребра обзора.
EDGE_TYPES: frozenset[str] = frozenset({"HAS_SUBCOMMUNITY", "HAS_REPORT", "INCLUDES_ENTITY"})

# The community summary artifact (label Finding) is a report, not a member entity.
_FINDING_LABEL = str(NodeLabel.FINDING)


def community_node_id(cid: int) -> str:
    """Deterministic node id for a community (кластер) — ``f'community:{cid}'``."""
    return f"community:{cid}"


def entity_node_id(entity_id: str) -> str:
    """Deterministic node id for a member entity (сущность) — ``f'entity:{eid}'``."""
    return f"entity:{entity_id}"


@dataclass(frozen=True)
class CommunityViewPayload:
    """Reagraph-style graph payload for the community view (§11.8 / §5.3).

    Attributes:
        nodes: tuple of node dicts, each ``{'id', 'label', 'type'}`` with ``type`` in
            :data:`NODE_TYPES`.
        edges: tuple of edge dicts, each ``{'source', 'target', 'type'}`` with ``type``
            in :data:`EDGE_TYPES`; ``source``/``target`` reference existing node ids.
    """

    nodes: tuple[dict[str, Any], ...] = ()
    edges: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a Reagraph-ready dict ``{'nodes': [...], 'edges': [...]}``.

        Copies the node/edge dicts so mutating the result never touches the frozen
        payload; every value is a plain ``str``/``list``/``dict`` (JSON-serialisable).
        """
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
        }


def _member_entities(
    store: KuzuGraphStore, cid: int, *, max_entities: int
) -> list[tuple[str, str]]:
    """Return up to ``max_entities`` ``(entity_id, label)`` members of a community.

    Members are the non-Finding nodes carrying ``community_id`` (the Finding summary is
    a report artifact). ``id``/``name`` are base columns, so they are read directly;
    results are sorted by id for determinism and capped at ``max_entities``.
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>$f RETURN n.id, n.name",
        {"c": cid, "f": _FINDING_LABEL},
    )
    members = sorted((str(nid), str(name or nid)) for nid, name in rows if nid)
    return members[:max_entities]


def build_community_view(
    store: KuzuGraphStore,
    used_community_ids: list[int],
    *,
    max_entities: int = 8,
    subcommunities: dict[int, list[int]] | None = None,
) -> CommunityViewPayload:
    """Assemble the §11.8 community-view payload over a KuzuGraphStore (§5.3).

    Emits one ``community`` node per id in ``used_community_ids``, up to ``max_entities``
    ``entity`` nodes per community (its member entities, read from the store) each joined
    by exactly one ``INCLUDES_ENTITY`` edge, and ``HAS_SUBCOMMUNITY`` edges taken from the
    ``subcommunities`` hierarchy mapping. Only hierarchy edges whose parent and child both
    have a community node (i.e. both appear in ``used_community_ids``) are kept, so every
    edge endpoint references an existing node id. An empty ``used_community_ids`` yields an
    empty payload. Deterministic and offline-safe.
    """
    used: list[int] = list(dict.fromkeys(used_community_ids))  # dedup, keep order
    used_set: set[int] = set(used)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for cid in used:
        cnode_id = community_node_id(cid)
        nodes[cnode_id] = {"id": cnode_id, "label": f"Community {cid}", "type": "community"}
        for eid, label in _member_entities(store, cid, max_entities=max_entities):
            enode_id = entity_node_id(eid)
            if enode_id not in nodes:
                nodes[enode_id] = {"id": enode_id, "label": label, "type": "entity"}
            edges.append({"source": cnode_id, "target": enode_id, "type": "INCLUDES_ENTITY"})

    for parent, children in (subcommunities or {}).items():
        if parent not in used_set:
            continue
        for child in children:
            if child not in used_set:
                continue
            edges.append(
                {
                    "source": community_node_id(parent),
                    "target": community_node_id(child),
                    "type": "HAS_SUBCOMMUNITY",
                }
            )

    _log.info(
        "community_view.build",
        communities=len(used),
        nodes=len(nodes),
        edges=len(edges),
    )
    return CommunityViewPayload(nodes=tuple(nodes.values()), edges=tuple(edges))
