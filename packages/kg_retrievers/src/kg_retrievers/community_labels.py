"""Auto-label communities from their top member entities (§11.12 авто-метки кластеров).

GraphRAG detection (:mod:`kg_retrievers.community`) writes a ``community_id`` back onto
entity nodes but leaves each community anonymous — good for indexing, poor for humans.
This module derives a short, deterministic Russian label (короткая метка) for a community
from the *names of its most connected member entities* (самые связанные сущности): the
members are ranked by their stored ``degree`` centrality and the highest-degree names are
folded into a ``Кластер: A, B, C`` label.

Offline-safe and read-only: no LLM, no clock, no writes. The store is only queried. An OSS
LLM can later rewrite the label into freeform prose; the template keeps a name here even
when no model is available.

Kuzu note: only the base columns of the ``Node`` table are queryable — ``community_id``,
``label`` and ``degree`` are base columns and so are RETURN-ed directly, while an entity's
display ``name`` is a custom prop read back through :meth:`KuzuGraphStore.get_node` (per
the store's column contract, §3 / ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import NodeLabel

_log = get_logger("community_labels")

# A community-summary Finding is a report artifact, not a member entity — exclude it so it
# never counts toward the size or supplies a "top entity" name.
_FINDING = str(NodeLabel.FINDING)

# RU prefix of the generated label (короткая метка кластера); empty members -> empty label.
_LABEL_PREFIX = "Кластер"


@dataclass(frozen=True)
class CommunityLabel:
    """Auto-generated label for one community (§11.12).

    Attributes:
        community_id: id of the community (кластер) this label describes.
        label: short RU label built from the top member names ('' if no members).
        top_entities: highest-degree member names, most-connected first (capped by ``top``).
        size: number of member entities in the community (Finding artifacts excluded).
    """

    community_id: int
    label: str
    top_entities: list[str] = field(default_factory=list)
    size: int = 0

    def as_dict(self) -> dict:
        """Serialise to a plain JSON-ready dict (copies the ``top_entities`` list)."""
        return {
            "community_id": self.community_id,
            "label": self.label,
            "top_entities": list(self.top_entities),
            "size": self.size,
        }


def _build_label(names: list[str]) -> str:
    """Fold top entity names into a short RU label; empty names -> empty label."""
    joined = ", ".join(n for n in names if n)
    return f"{_LABEL_PREFIX}: {joined}" if joined else ""


def _entity_name(store: KuzuGraphStore, node_id: str) -> str:
    """Read an entity's display name via get_node (custom prop), falling back to id."""
    node = store.get_node(node_id)
    if not node:
        return node_id
    return str(node.get("name") or node.get("canonical_name") or node_id)


def label_community(store: KuzuGraphStore, community_id: int, *, top: int = 3) -> CommunityLabel:
    """Label a community from the names of its ``top`` highest-degree members (§11.12).

    Members are the non-Finding nodes carrying ``community_id``; ``degree`` is a base column
    so it is RETURN-ed directly and used to rank members (missing degree sorts as 0, ties
    broken by id for determinism). The highest-degree ids are resolved to display names via
    :func:`_entity_name` and folded into a short RU label. An unknown/empty community yields
    an empty label, no top entities and ``size == 0`` (not an error).
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>$f RETURN n.id, n.degree",
        {"c": community_id, "f": _FINDING},
    )
    members = [(nid, deg) for nid, deg in rows if nid]
    members.sort(key=lambda pair: (-(pair[1] or 0), pair[0]))
    top_ids = [nid for nid, _ in members[: max(0, top)]]
    names = [_entity_name(store, nid) for nid in top_ids]
    result = CommunityLabel(
        community_id=community_id,
        label=_build_label(names),
        top_entities=names,
        size=len(members),
    )
    _log.info("community_labels.label", community_id=community_id, size=result.size, top=len(names))
    return result


def label_all_communities(store: KuzuGraphStore, *, top: int = 3) -> list[CommunityLabel]:
    """Label every community in the store — one :class:`CommunityLabel` each (§11.12).

    Distinct ``community_id`` values are collected over the entity members (Finding artifacts
    excluded) and labelled in ascending id order for a stable result. An empty store yields
    an empty list.
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id IS NOT NULL AND n.label<>$f RETURN n.community_id",
        {"f": _FINDING},
    )
    cids = sorted({int(r[0]) for r in rows if r[0] is not None})
    labels = [label_community(store, cid, top=top) for cid in cids]
    _log.info("community_labels.label_all", communities=len(labels))
    return labels
