"""Hybrid retrieval (§12): reciprocal-rank fusion of vector + keyword search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.keyword_store import KeywordStore
from kg_retrievers.vector_store import VectorStore

_log = get_logger("hybrid")
RRF_K = 60


@dataclass
class FusedHit:
    id: str
    score: float
    payload: dict[str, Any]


class HybridRetriever:
    def __init__(
        self, vector: VectorStore | None = None, keyword: KeywordStore | None = None
    ) -> None:
        self.vector = vector
        self.keyword = keyword

    def available(self) -> bool:
        vc = self.vector.count() if self.vector else 0
        kc = self.keyword.count() if self.keyword else 0
        return (vc + kc) > 0

    def search(self, query: str, limit: int = 8) -> list[FusedHit]:
        ranks: dict[str, float] = {}
        payloads: dict[str, dict[str, Any]] = {}
        if self.vector:
            for rank, hit in enumerate(self.vector.search(query, limit * 2)):
                ranks[hit.id] = ranks.get(hit.id, 0.0) + 1.0 / (RRF_K + rank)
                payloads.setdefault(hit.id, hit.payload)
        if self.keyword:
            for rank, hit in enumerate(self.keyword.search(query, limit * 2)):
                ranks[hit.id] = ranks.get(hit.id, 0.0) + 1.0 / (RRF_K + rank)
                payloads.setdefault(hit.id, hit.payload)
        ordered = sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [FusedHit(id=i, score=s, payload=payloads.get(i, {})) for i, s in ordered]

    @classmethod
    def open_default(cls) -> HybridRetriever:
        """Open the on-disk stores if present (graceful if empty)."""
        try:
            vec = VectorStore()
        except Exception as exc:
            _log.warning("hybrid.vector_unavailable", error=str(exc)[:100])
            vec = None
        return cls(vector=vec, keyword=KeywordStore())
