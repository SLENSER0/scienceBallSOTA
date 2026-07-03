"""Dense vector store over a **live Qdrant server** (§4.5 server profile).

Профиль сервера: unlike :class:`kg_retrievers.vector_store.VectorStore` (which
drives Qdrant in embedded / on-disk mode with the same client API), this store
talks to a running Qdrant daemon over HTTP (``QdrantClient(url=...)``). It stores
chunk passages with structured payload for semantic retrieval and evidence
assembly, and constrains searches with :mod:`kg_retrievers.vector_filters`
payload filters translated to the server's ``Filter`` JSON via :func:`to_qdrant`.

Chunk id → point id: Qdrant point ids must be ``int`` or UUID, but chunk ids are
free-form strings; we derive a deterministic ``uuid5`` so re-upserting the same
chunk id updates in place (idempotent, идемпотентно) instead of duplicating.
"""

from __future__ import annotations

import uuid
from typing import Any

from kg_common import get_logger, get_settings
from kg_retrievers.embeddings import dim as embed_dim
from kg_retrievers.embeddings import embed, embed_one
from kg_retrievers.vector_filters import Filter, to_qdrant

_log = get_logger("qdrant_server_store")

# Fixed namespace so a given chunk id always maps to the same point id (§4.5);
# shared with the embedded VectorStore for cross-profile point-id parity.
_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


class QdrantServerStore:
    """Dense vector store backed by a live Qdrant server (§4.5)."""

    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        from qdrant_client import QdrantClient

        s = get_settings()
        self.url = url or s.qdrant_url
        self.collection = collection or s.qdrant_collection
        self.client = QdrantClient(url=self.url)

    # -- point-id derivation ----------------------------------------------
    def _pid(self, key: str) -> str:
        """Deterministic ``uuid5`` point id for a free-form chunk id (§4.5)."""
        return str(uuid.uuid5(_NS, str(key)))

    # -- collection lifecycle ---------------------------------------------
    def ensure_collection(self, dim: int | None = None) -> None:
        """Create (or recreate) the collection with Cosine distance (§4.5).

        ``dim`` defaults to the embeddings dimension. A pre-existing collection
        is dropped first so the vector size/metric always match the model —
        recreate, а не миграция.
        """
        from qdrant_client.models import Distance, VectorParams

        size = dim if dim is not None else embed_dim()
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
        _log.info("qdrant_server.ensure", collection=self.collection, dim=size)

    # -- write ------------------------------------------------------------
    def upsert_chunks(self, chunks: list[dict[str, Any]], *, batch: int = 128) -> int:
        """Embed and upsert ``[{id, text, doc_id, page, material_ids?}]`` (§4.5).

        Returns the number of points written. Embeds each batch's ``text`` and
        stores the original chunk id plus metadata in the payload.
        """
        from qdrant_client.models import PointStruct

        n = 0
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            vecs = embed([c["text"] for c in part])
            points = [
                PointStruct(
                    id=self._pid(c["id"]),
                    vector=vec,
                    payload={
                        "chunk_id": c["id"],
                        "text": c["text"],
                        "doc_id": c.get("doc_id"),
                        "page": c.get("page"),
                        "material_ids": c.get("material_ids", []),
                    },
                )
                for c, vec in zip(part, vecs, strict=False)
            ]
            self.client.upsert(self.collection, points=points, wait=True)
            n += len(points)
        return n

    # -- read -------------------------------------------------------------
    def _to_query_filter(self, flt: Filter | dict | None) -> Any:
        """Translate an optional payload filter to a Qdrant ``Filter`` (§4.5).

        A :class:`~kg_retrievers.vector_filters.Filter` is rendered via
        :func:`to_qdrant`; a plain dict is passed through the same JSON shape; a
        ready ``qdrant_client`` model (or ``None``) is used as-is.
        """
        if flt is None:
            return None
        from qdrant_client.models import Filter as QFilter

        if isinstance(flt, Filter):
            return QFilter(**to_qdrant(flt))
        if isinstance(flt, dict):
            return QFilter(**flt)
        return flt

    def search(
        self, query: str, top_k: int = 5, flt: Filter | dict | None = None
    ) -> list[dict[str, Any]]:
        """Semantic search returning ``[{id, text, score, doc_id, page}]`` (§4.5).

        The query is embedded and matched by Cosine similarity; an optional
        payload ``flt`` narrows the candidates server-side.
        """
        vec = embed_one(query)
        if not vec:
            return []
        res = self.client.query_points(
            self.collection,
            query=vec,
            limit=top_k,
            query_filter=self._to_query_filter(flt),
            with_payload=True,
        )
        return [
            {
                "id": p.payload.get("chunk_id", str(p.id)),
                "text": p.payload.get("text", ""),
                "score": p.score,
                "doc_id": p.payload.get("doc_id"),
                "page": p.payload.get("page"),
            }
            for p in res.points
        ]

    # -- delete / count ---------------------------------------------------
    def delete_by_doc(self, doc_id: str) -> None:
        """Delete every point whose payload ``doc_id`` matches (§4.5)."""
        from qdrant_client.models import FieldCondition, MatchValue
        from qdrant_client.models import Filter as QFilter

        self.client.delete(
            self.collection,
            points_selector=QFilter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
            wait=True,
        )

    def count(self) -> int:
        """Exact number of points currently stored (§4.5)."""
        return self.client.count(self.collection, exact=True).count
