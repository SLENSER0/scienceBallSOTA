"""Hybrid retrieval (§12): reciprocal-rank fusion of vector + keyword search."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
        # Each channel is fused independently and defensively: a single dead backend
        # (e.g. an OpenSearch index that vanished after a container restart) must
        # DEGRADE the result, never 500 the whole query. See kg_chunks 404 incident.
        #
        # The vector and keyword channels are fully independent — vector spends
        # ~2.5s embedding the query on CPU plus a Qdrant round-trip, keyword runs a
        # GIL-releasing BM25 scan / OpenSearch round-trip — so we fire both on a
        # 2-worker pool and overlap them (wall time ~max instead of ~sum). Каналы
        # запускаются параллельно, слияние остаётся однопоточным. Fusion below is
        # unchanged: we collect ``.result()`` in the SAME original channel order
        # (vector then keyword) so the RRF rank sums and payloads.setdefault
        # first-wins tie-breaking are byte-identical to the old sequential loop,
        # and the per-channel try/except still degrades past any backend fault.
        channels = [
            (c, n) for c, n in ((self.vector, "vector"), (self.keyword, "keyword")) if c
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                (pool.submit(channel.search, query, limit * 2), name)
                for channel, name in channels
            ]
            for future, name in futures:
                try:
                    hits = future.result()
                except Exception as exc:  # degrade past any backend fault (missing index, timeout)
                    _log.warning("hybrid.channel_failed", channel=name, error=str(exc)[:150])
                    continue
                for rank, hit in enumerate(hits):
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
