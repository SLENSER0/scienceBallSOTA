"""Assembled Entity Detail view-model over a Kuzu graph store (§5.2.4 / §17.11).

Читает засеянный :class:`KuzuGraphStore` и собирает секции экрана Entity Detail
(§5.2.4) для одной сущности: заголовок (canonical name, тип, confidence, статус
review + флаг ``verified``), алиасы, связанные узлы, сгруппированные по типу связи
(исходящие / входящие), и счётчик доказательств (рёбра ``SUPPORTED_BY``).

Чистый слой чтения: центр берётся через :meth:`KuzuGraphStore.get_node`, соседи —
через :meth:`KuzuGraphStore.neighbors` (§5.3 payload), из рёбер которого выводятся
направление и тип связи. Полные словари связанных узлов дочитываются через
``get_node`` (Kuzu note: кастомные props — не колонки, доступны только так).

This is an assembled view-model (no I/O beyond the injected store, deterministic).
``verified`` reuses :data:`kg_retrievers.graph_dto.VERIFIED_STATUSES` so the lock
icon on this screen matches the graph payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_dto import VERIFIED_STATUSES
from kg_retrievers.graph_store import KuzuGraphStore

# RelType whose incident edges are counted as supporting evidence (§3.7 / §5.2.4).
_EVIDENCE_REL_TYPE = "SUPPORTED_BY"


def _parse_aliases(raw: Any) -> tuple[str, ...]:
    """Normalise an ``aliases`` value (list / ``|``-joined / JSON string) to a tuple."""
    if not raw:
        return ()
    if isinstance(raw, (list, tuple, set)):
        return tuple(str(x) for x in raw if str(x))
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, list):
                return tuple(str(x) for x in parsed if str(x))
        # fall back to the store's pipe-delimited ``aliases_text`` convention
        return tuple(p for p in (s.strip() for s in text.split("|")) if p)
    return ()


def _aliases_of(node: dict[str, Any]) -> tuple[str, ...]:
    """Aliases from an ``aliases`` prop, falling back to the ``aliases_text`` column."""
    if node.get("aliases") is not None:
        return _parse_aliases(node.get("aliases"))
    return _parse_aliases(node.get("aliases_text"))


@dataclass(frozen=True)
class EntityDetailView:
    """Assembled §5.2.4 Entity Detail sections for one entity (frozen view-model)."""

    entity_id: str
    canonical_name: str
    entity_type: str
    confidence: float | None
    review_status: str
    verified: bool
    aliases: tuple[str, ...]
    outgoing: dict[str, tuple[dict[str, Any], ...]]
    incoming: dict[str, tuple[dict[str, Any], ...]]
    evidence_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready camelCase payload (plain dicts / lists only)."""
        return {
            "entityId": self.entity_id,
            "canonicalName": self.canonical_name,
            "entityType": self.entity_type,
            "confidence": self.confidence,
            "reviewStatus": self.review_status,
            "verified": self.verified,
            "aliases": list(self.aliases),
            "outgoingByType": {k: [dict(n) for n in v] for k, v in self.outgoing.items()},
            "incomingByType": {k: [dict(n) for n in v] for k, v in self.incoming.items()},
            "evidenceCount": self.evidence_count,
        }


def _as_float(value: Any) -> float | None:
    """Coerce to ``float`` or ``None`` (never raises)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _grouped_neighbors(
    store: KuzuGraphStore, entity_id: str
) -> tuple[dict[str, tuple[dict[str, Any], ...]], dict[str, tuple[dict[str, Any], ...]]]:
    """Walk :meth:`neighbors` and group related node dicts by RelType and direction."""
    response = store.neighbors(entity_id, depth=1)
    cache: dict[str, dict[str, Any] | None] = {}

    def _load(node_id: str) -> dict[str, Any] | None:
        if node_id not in cache:
            cache[node_id] = store.get_node(node_id)
        return cache[node_id]

    out: dict[str, list[dict[str, Any]]] = {}
    inc: dict[str, list[dict[str, Any]]] = {}
    seen_out: set[tuple[str, str]] = set()
    seen_inc: set[tuple[str, str]] = set()
    for edge in response.edges:
        if edge.source == entity_id and edge.target != entity_id:
            if (edge.type, edge.target) in seen_out:
                continue
            node = _load(edge.target)
            if node is not None:
                seen_out.add((edge.type, edge.target))
                out.setdefault(edge.type, []).append(node)
        elif edge.target == entity_id and edge.source != entity_id:
            if (edge.type, edge.source) in seen_inc:
                continue
            node = _load(edge.source)
            if node is not None:
                seen_inc.add((edge.type, edge.source))
                inc.setdefault(edge.type, []).append(node)
    return (
        {k: tuple(v) for k, v in out.items()},
        {k: tuple(v) for k, v in inc.items()},
    )


def _evidence_count(store: KuzuGraphStore, entity_id: str) -> int:
    """Count ``SUPPORTED_BY`` edges incident to ``entity_id`` (either direction)."""
    total = 0
    for pattern in (
        "MATCH (:Node {id:$id})-[r:Rel]->(:Node) WHERE r.type=$t RETURN count(r)",
        "MATCH (:Node {id:$id})<-[r:Rel]-(:Node) WHERE r.type=$t RETURN count(r)",
    ):
        rows = store.rows(pattern, {"id": entity_id, "t": _EVIDENCE_REL_TYPE})
        if rows and rows[0]:
            total += int(rows[0][0])
    return total


def build_entity_detail(store: KuzuGraphStore, entity_id: str) -> EntityDetailView | None:
    """Assemble the §5.2.4 Entity Detail view for ``entity_id`` (``None`` if absent).

    Reads the center via :meth:`get_node`; returns ``None`` when the node does not
    exist. ``canonical_name`` prefers the ``canonical_name`` column, then ``name``,
    then the id. ``verified`` is ``review_status`` ∈ :data:`VERIFIED_STATUSES`. Related
    nodes are grouped by RelType into ``outgoing`` / ``incoming`` via
    :func:`_grouped_neighbors`; ``evidence_count`` is the number of ``SUPPORTED_BY``
    edges incident to the entity.
    """
    center = store.get_node(entity_id)
    if center is None:
        return None
    review_status = str(center.get("review_status") or "")
    canonical_name = str(center.get("canonical_name") or center.get("name") or entity_id)
    outgoing, incoming = _grouped_neighbors(store, entity_id)
    return EntityDetailView(
        entity_id=entity_id,
        canonical_name=canonical_name,
        entity_type=str(center.get("label") or "Entity"),
        confidence=_as_float(center.get("confidence")),
        review_status=review_status,
        verified=review_status in VERIFIED_STATUSES,
        aliases=_aliases_of(center),
        outgoing=outgoing,
        incoming=incoming,
        evidence_count=_evidence_count(store, entity_id),
    )


__all__ = ["EntityDetailView", "build_entity_detail"]
