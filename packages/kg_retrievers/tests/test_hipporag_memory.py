"""HippoRAG-2 PPR memory retrieval tests (§12.5, arXiv:2502.14802).

Hand-checkable graphs over fresh temp Kuzu stores:

- a dense entity cluster ``c1<->c2<->c3`` plus a disconnected ``f1<->f2`` pair —
  seeding ``c1`` must rank the whole cluster above the far pair;
- a chain ``s->h1->h2`` plus a disconnected ``u1<->u2`` pair — the multi-hop-reachable
  ``h2`` must score above the unrelated ``u1`` (activation spreads, teleport does not);
- entities backed by Evidence carrying ``doc_id`` — the supporting docs are gathered;
- unknown seed / empty store degrade gracefully; ``top_k`` caps; ``as_dict`` shape;
  the module docstring cites the source paper (arXiv:2502.14802).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers import hipporag_memory
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.hipporag_memory import MemoryResult, hipporag_retrieve


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _ent(store: KuzuGraphStore, nid: str) -> None:
    # 'Material' is in ENTITY_LABELS, so the node enters the PPR projection.
    store.upsert_node(nid, "Material", name=nid)


def _link(store: KuzuGraphStore, a: str, b: str) -> None:
    store.upsert_edge(a, b, "RELATED_TO")


def _bilink(store: KuzuGraphStore, a: str, b: str) -> None:
    _link(store, a, b)
    _link(store, b, a)


def _cluster_store() -> KuzuGraphStore:
    """Dense cluster c1<->c2<->c3<->c1, plus a disconnected far pair f1<->f2."""
    store = _store()
    for nid in ("c1", "c2", "c3", "f1", "f2"):
        _ent(store, nid)
    _bilink(store, "c1", "c2")
    _bilink(store, "c2", "c3")
    _bilink(store, "c1", "c3")
    _bilink(store, "f1", "f2")
    return store


def _scores(result: MemoryResult) -> dict[str, float]:
    return {r["id"]: r["score"] for r in result.ranked}


def test_seed_near_cluster_ranks_cluster_high() -> None:
    store = _cluster_store()
    result = hipporag_retrieve(store, ["c1"], top_k=3)
    assert {r["id"] for r in result.ranked} == {"c1", "c2", "c3"}
    scores = _scores(result)
    # every cluster member outranks the disconnected far pair (which gets no mass).
    full = hipporag_retrieve(store, ["c1"], top_k=10)
    far = _scores(full)
    assert min(scores.values()) > max(far["f1"], far["f2"])


def test_multihop_entity_outranks_unrelated() -> None:
    store = _store()
    for nid in ("s", "h1", "h2", "u1", "u2"):
        _ent(store, nid)
    _link(store, "s", "h1")  # 1 hop from seed
    _link(store, "h1", "h2")  # 2 hops from seed — reachable only via PPR spread
    _bilink(store, "u1", "u2")  # disconnected component — unrelated to the seed
    scores = _scores(hipporag_retrieve(store, ["s"], top_k=10))
    # activation reaches the multi-hop node; the unrelated node stays at ~0.
    assert scores["h2"] > scores["u1"]
    assert scores["h2"] > 0.0
    assert scores["u1"] == pytest.approx(0.0, abs=1e-9)


def test_doc_ids_gathered() -> None:
    store = _store()
    _ent(store, "m1")
    _ent(store, "m2")
    _bilink(store, "m1", "m2")
    # Evidence nodes are NOT entities, so SUPPORTED_BY edges stay out of the PPR graph.
    store.upsert_node("ev1", "Evidence", doc_id="docA")
    store.upsert_node("ev2", "Evidence", doc_id="docB")
    store.upsert_edge("m1", "ev1", "SUPPORTED_BY")
    store.upsert_edge("m2", "ev2", "SUPPORTED_BY")
    result = hipporag_retrieve(store, ["m1"], top_k=10)
    assert result.doc_ids == ["docA", "docB"]


def test_doc_ids_capped_to_top_k() -> None:
    store = _store()
    _ent(store, "m1")
    _ent(store, "m2")
    _bilink(store, "m1", "m2")
    store.upsert_node("ev1", "Evidence", doc_id="docA")
    store.upsert_node("ev2", "Evidence", doc_id="docB")
    store.upsert_edge("m1", "ev1", "SUPPORTED_BY")
    store.upsert_edge("m2", "ev2", "SUPPORTED_BY")
    # top_k=1 keeps only the seed m1 -> only its supporting doc is gathered.
    result = hipporag_retrieve(store, ["m1"], top_k=1)
    assert [r["id"] for r in result.ranked] == ["m1"]
    assert result.doc_ids == ["docA"]


def test_no_evidence_yields_empty_doc_ids() -> None:
    store = _store()
    _ent(store, "x")
    _ent(store, "y")
    _bilink(store, "x", "y")
    result = hipporag_retrieve(store, ["x"], top_k=10)
    assert result.doc_ids == []


def test_unknown_seed_graceful() -> None:
    store = _cluster_store()
    result = hipporag_retrieve(store, ["nonexistent"], top_k=10)
    # falls back to a uniform restart (plain PageRank) — no error, full ranking.
    assert isinstance(result, MemoryResult)
    assert result.seeds == ["nonexistent"]
    assert {r["id"] for r in result.ranked} == {"c1", "c2", "c3", "f1", "f2"}


def test_empty_store_graceful() -> None:
    store = _store()
    result = hipporag_retrieve(store, ["x"], top_k=5)
    assert result.ranked == []
    assert result.doc_ids == []
    assert result.seeds == ["x"]


def test_top_k_caps_ranked() -> None:
    store = _cluster_store()
    result = hipporag_retrieve(store, ["c1"], top_k=2)
    assert len(result.ranked) == 2


def test_as_dict_shape() -> None:
    result = MemoryResult(
        seeds=["c1"],
        ranked=[{"id": "c1", "score": 0.4}, {"id": "c2", "score": 0.3}],
        doc_ids=["docA"],
    )
    assert result.as_dict() == {
        "seeds": ["c1"],
        "ranked": [{"id": "c1", "score": 0.4}, {"id": "c2", "score": 0.3}],
        "doc_ids": ["docA"],
    }
    # round-trip from a real retrieval keeps the documented shape.
    live = hipporag_retrieve(_cluster_store(), ["c1"], top_k=3).as_dict()
    assert set(live) == {"seeds", "ranked", "doc_ids"}
    assert all(set(r) == {"id", "score"} for r in live["ranked"])


def test_docstring_cites_paper() -> None:
    assert "2502.14802" in (hipporag_memory.__doc__ or "")
