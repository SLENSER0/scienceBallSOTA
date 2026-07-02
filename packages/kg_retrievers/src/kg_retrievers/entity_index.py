"""Entity-level semantic index over Qdrant local (§3.13 / §4.5 / §4.6).

Complements the chunk-level :class:`~kg_retrievers.vector_store.VectorStore` with an
*entity* vector space: each resolvable ``:Entity`` node (§3.4 ``ENTITY_LABELS``) is
embedded from its surface form (name + aliases) into an ``kg_entities`` collection.
A free-text mention — or another entity's id — then resolves to the nearest canonical
entities, powering entity linking / "similar entities" (§4.5) and query grounding
(§4.6). Reuses the VectorStore-on-Qdrant pattern (§4 / ADR-0005/0006).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from kg_common import get_logger, get_settings
from kg_retrievers.embeddings import dim, embed, embed_one
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

_log = get_logger("entity_index")
_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

# Surface + canonical descriptor fields folded into one embeddable string. Names and
# aliases carry the mention forms (§3.13); the descriptors (operation / domain /
# material_class) add the discriminating context that lets a process mention such as
# "electrowinning" ground onto the right catholyte / electrolyte entities (§4.5).
_TEXT_FIELDS = (
    "name",
    "canonical_name",
    "aliases_text",
    "operation",
    "domain",
    "material_class",
)


@dataclass
class EntityHit:
    id: str
    score: float
    label: str
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


def _entity_text(node: dict[str, Any]) -> str:
    """Build the embeddable surface string from a node's name + aliases (§3.13)."""
    seen: set[str] = set()
    parts: list[str] = []
    for key in _TEXT_FIELDS:
        val = node.get(key)
        if not val:
            continue
        text = str(val).strip()
        if text and text not in seen:
            seen.add(text)
            parts.append(text)
    return " ".join(parts)


class EntityVectorIndex:
    """Nearest-entity search over an ``kg_entities`` Qdrant collection (§4.5)."""

    def __init__(self, collection: str | None = None, *, on_disk: bool = True) -> None:
        from qdrant_client import QdrantClient

        s = get_settings()
        self.collection = collection or s.qdrant_entity_collection
        if on_disk:
            self.client = QdrantClient(path=s.qdrant_path)
        else:
            self.client = QdrantClient(":memory:")
        self._ensure()

    def _ensure(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                self.collection,
                vectors_config=VectorParams(size=dim(), distance=Distance.COSINE),
            )

    def _pid(self, key: str) -> str:
        return str(uuid.uuid5(_NS, key))

    # -- write -----------------------------------------------------------
    def index_entities(self, store: KuzuGraphStore, *, batch: int = 128) -> int:
        """Embed every resolvable :Entity node (name + aliases) into the collection.

        Returns the number of entities indexed. Idempotent: point ids are derived
        from the entity id, so re-indexing overwrites in place.
        """
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label IN $labels "
            "AND (n.name IS NOT NULL OR n.aliases_text IS NOT NULL) RETURN n",
            {"labels": list(ENTITY_LABELS)},
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            node = store._node_dict(row[0])
            text = _entity_text(node)
            if not text or "id" not in node:
                continue
            items.append(
                {
                    "id": node["id"],
                    "text": text,
                    "label": node.get("label", "Entity"),
                    "name": node.get("name") or node.get("canonical_name") or node["id"],
                }
            )
        return self._upsert(items, batch=batch)

    def _upsert(self, items: list[dict[str, Any]], *, batch: int) -> int:
        from qdrant_client.models import PointStruct

        n = 0
        for i in range(0, len(items), batch):
            chunk = items[i : i + batch]
            vecs = embed([it["text"] for it in chunk])
            points = [
                PointStruct(
                    id=self._pid(it["id"]),
                    vector=v,
                    payload={
                        "ref_id": it["id"],
                        "label": it["label"],
                        "name": it["name"],
                        "text": it["text"][:500],
                    },
                )
                for it, v in zip(chunk, vecs, strict=False)
            ]
            self.client.upsert(self.collection, points=points)
            n += len(points)
        _log.info("entity_index.done", indexed=n, collection=self.collection)
        return n

    # -- read ------------------------------------------------------------
    def similar_entities(self, query_or_id: str, k: int = 8) -> list[EntityHit]:
        """Nearest entities to a free-text mention *or* an existing entity id.

        If ``query_or_id`` matches an indexed entity id, that entity's stored vector
        is used and the entity itself is excluded from the results; otherwise the
        string is embedded as a query.
        """
        vec, exclude = self._resolve_vector(query_or_id)
        if not vec:
            return []
        res = self.client.query_points(
            self.collection,
            query=vec,
            limit=k + 1 if exclude else k,
            with_payload=True,
        )
        hits: list[EntityHit] = []
        for p in res.points:
            ref = p.payload.get("ref_id", str(p.id))
            if exclude is not None and ref == exclude:
                continue
            hits.append(
                EntityHit(
                    id=ref,
                    score=p.score,
                    label=p.payload.get("label", "Entity"),
                    name=p.payload.get("name", ref),
                    payload=p.payload,
                )
            )
        return hits[:k]

    def _resolve_vector(self, query_or_id: str) -> tuple[list[float], str | None]:
        """Return ``(vector, excluded_id)`` — reuse a stored entity vector if id hits."""
        try:
            recs = self.client.retrieve(
                self.collection, ids=[self._pid(query_or_id)], with_vectors=True
            )
        except Exception:  # malformed key / empty collection
            recs = []
        if recs and recs[0].vector:
            return list(recs[0].vector), query_or_id  # type: ignore[arg-type]
        return embed_one(query_or_id), None

    def count(self) -> int:
        return self.client.count(self.collection).count
