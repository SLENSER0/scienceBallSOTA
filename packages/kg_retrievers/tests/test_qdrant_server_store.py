"""Live round-trip test for :class:`QdrantServerStore` (§4.5 server profile).

Hits the real Qdrant daemon on ``localhost:6333`` with a unique per-process
collection, indexes real embeddings, exercises search / payload filter / delete
/ count, then drops its own collection. Skips only if the server is genuinely
unreachable (no random module, no network mocks).
"""

from __future__ import annotations

import contextlib
import os

import pytest

from kg_retrievers.qdrant_server_store import QdrantServerStore
from kg_retrievers.vector_filters import build_filter

_URL = "http://localhost:6333"

# Three chunks across two docs; each text is clearly about a distinct material
# so a matching query has an unambiguous nearest neighbour.
_CHUNKS = [
    {
        "id": "c1",
        "text": "stainless steel strongly resists corrosion in marine seawater",
        "doc_id": "docA",
        "page": 1,
        "material_ids": ["steel"],
    },
    {
        "id": "c2",
        "text": "aluminium alloys are prized for high thermal conductivity",
        "doc_id": "docB",
        "page": 2,
        "material_ids": ["aluminium"],
    },
    {
        "id": "c3",
        "text": "titanium exhibits excellent fatigue strength under cyclic load",
        "doc_id": "docA",
        "page": 3,
        "material_ids": ["titanium"],
    },
]


def _server_up(url: str) -> bool:
    """True iff a live Qdrant answers at ``url`` (§4.5)."""
    try:
        from qdrant_client import QdrantClient

        QdrantClient(url=url).get_collections()
        return True
    except Exception:  # any transport/handshake error = server unreachable
        return False


@pytest.fixture
def store():
    """A store on a unique ``t_qdrant_<pid>`` collection, dropped on teardown."""
    if not _server_up(_URL):
        pytest.skip(f"live Qdrant server unreachable at {_URL}")
    name = f"t_qdrant_{os.getpid()}"
    s = QdrantServerStore(url=_URL, collection=name)
    try:
        yield s
    finally:
        with contextlib.suppress(Exception):  # best-effort teardown
            s.client.delete_collection(name)


def test_qdrant_server_store_live_roundtrip(store: QdrantServerStore) -> None:
    """Full lifecycle against the live server (§4.5)."""
    # 1) ensure_collection creates the collection.
    store.ensure_collection(384)
    assert store.client.collection_exists(store.collection)

    # 2) upsert 3 chunks -> returns the count written, 3) count reflects it.
    n = store.upsert_chunks(_CHUNKS)
    assert n == 3
    assert store.count() == 3

    # 4) a matching query returns the most-similar chunk first.
    hits = store.search("corrosion resistance of stainless steel", top_k=3)
    assert hits, "search returned no hits"
    assert hits[0]["id"] == "c1"

    # 5) every hit dict carries the documented keys.
    assert set(hits[0]) == {"id", "text", "score", "doc_id", "page"}
    assert hits[0]["doc_id"] == "docA"
    assert hits[0]["page"] == 1

    # 6) a payload filter narrows results to a single doc.
    flt = build_filter(doc_id="docB")
    narrowed = store.search("metal properties", top_k=3, flt=flt)
    assert narrowed, "filtered search returned no hits"
    assert {h["doc_id"] for h in narrowed} == {"docB"}
    assert {h["id"] for h in narrowed} == {"c2"}

    # 7) delete_by_doc removes matching points; count drops accordingly.
    store.delete_by_doc("docA")
    assert store.count() == 1
    remaining = store.search("materials", top_k=5)
    assert {h["id"] for h in remaining} == {"c2"}
