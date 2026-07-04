"""Vector store over Qdrant local mode (§4 / ADR-0005).

Same client API as a Qdrant server, but on-disk/in-memory — no daemon. Stores
chunk passages with payload for semantic retrieval and evidence assembly.
"""

from __future__ import annotations

import functools
import uuid
from dataclasses import dataclass
from typing import Any

from kg_common import get_logger, get_settings
from kg_retrievers.embeddings import dim, embed, embed_one

_log = get_logger("vector_store")
_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


@functools.lru_cache(maxsize=256)
def _embed_query(q: str) -> tuple[float, ...]:
    """Memoized query embedding — кэш эмбеддинга запроса (query-path only).

    The embedding model is deterministic, so caching identical query text is
    behavior-preserving: a repeat query skips the ~2.5s CPU model inference and
    reuses the in-memory vector. Only the read/search path is cached; indexing
    goes through :func:`embed` (batched) and is untouched. Returned as an
    immutable tuple so the cache value cannot be mutated by callers.
    """
    return tuple(embed_one(q))


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict[str, Any]


class VectorStore:
    def __init__(self, collection: str | None = None, *, on_disk: bool = True) -> None:
        from qdrant_client import QdrantClient

        s = get_settings()
        self.collection = collection or s.qdrant_collection
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

    def index(self, items: list[dict[str, Any]], *, batch: int = 128) -> int:
        """Index ``[{id, text, payload}]``. Returns count indexed."""
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
                        **it.get("payload", {}),
                        "text": it["text"][:1000],
                    },
                )
                for it, v in zip(chunk, vecs, strict=False)
            ]
            self.client.upsert(self.collection, points=points)
            n += len(points)
        return n

    def search(self, query: str, limit: int = 8) -> list[VectorHit]:
        vec = list(_embed_query(query))
        if not vec:
            return []
        res = self.client.query_points(self.collection, query=vec, limit=limit, with_payload=True)
        return [
            VectorHit(id=p.payload.get("ref_id", str(p.id)), score=p.score, payload=p.payload)
            for p in res.points
        ]

    def count(self) -> int:
        return self.client.count(self.collection).count
