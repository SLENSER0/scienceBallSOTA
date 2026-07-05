"""Destructive corpus-source purge tests (§2/§4).

Hand-checkable graph on a fresh temp Kuzu store: one source Document «doc:demo» with
three derived nodes (Chunk / Evidence / Measurement) carrying ``doc_id=doc:demo``, plus
a SHARED Material «nickel» that has NO ``doc_id`` and a different ``id``. Purging the
source must remove the document and everything derived from it (nodes AND edges) while
the shared canonical Material SURVIVES; a second purge is a no-op (0 nodes). Side stores
(registry / vector) are exercised with in-memory fakes, including the guarded failure
path where a failing vector store must NOT abort the graph delete.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.source_delete import delete_source_nodes, purge_source

_DOC = "doc:demo"


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    """Source doc + derived nodes (doc_id=doc:demo) + a shared, doc_id-less Material."""
    s.upsert_node(_DOC, "Document", name="demo report")  # the source (matched by id)
    s.upsert_node("chunk:1", "Chunk", text="passage", doc_id=_DOC, page=1)
    s.upsert_node("ev:1", "Evidence", text="плотность тока 250 А/м²", doc_id=_DOC, page=1)
    s.upsert_node(
        "meas:1", "Measurement", property_name="current_density", value_normalized=250.0,
        doc_id=_DOC,
    )
    # SHARED canonical entity — no doc_id, different id -> must survive the purge.
    s.upsert_node("material:ni", "Material", name="nickel", canonical_name="nickel")
    # Edges: doc->chunk->ev, meas->ev, and meas -> shared Material (crosses the boundary).
    s.upsert_edge(_DOC, "chunk:1", "HAS_CHUNK")
    s.upsert_edge("chunk:1", "ev:1", "CONTAINS")
    s.upsert_edge("meas:1", "ev:1", "SUPPORTED_BY", evidence_ids=["ev:1"])
    s.upsert_edge("meas:1", "material:ni", "ABOUT_MATERIAL")


def test_cascade_removes_source_and_derived_only(store: KuzuGraphStore) -> None:
    _seed(store)
    assert store.counts() == {"nodes": 5, "rels": 4}

    out = purge_source(store, _DOC)

    # source + its 3 derived nodes gone; shared Material survives (§2).
    assert out["deleted_nodes"] == 4
    for gone in (_DOC, "chunk:1", "ev:1", "meas:1"):
        assert store.get_node(gone) is None
    survivor = store.get_node("material:ni")
    assert survivor is not None and survivor["name"] == "nickel"
    assert store.counts()["nodes"] == 1  # only the shared Material remains


def test_all_edges_to_deleted_nodes_are_gone(store: KuzuGraphStore) -> None:
    _seed(store)
    purge_source(store, _DOC)
    # DETACH DELETE removed every edge touching a deleted node — including the
    # meas:1 -> material:ni edge that crossed into the surviving Material.
    assert store.counts()["rels"] == 0
    assert store.edges_among({"material:ni"}) == []


def test_idempotent_second_purge_is_noop(store: KuzuGraphStore) -> None:
    _seed(store)
    assert purge_source(store, _DOC)["deleted_nodes"] == 4
    # Second purge of the now-absent source: 0 nodes, not an error (§4).
    again = purge_source(store, _DOC)
    assert again == {
        "source_id": _DOC,
        "deleted_nodes": 0,
        "registry_deleted": False,
        "vector_purged": False,
    }
    assert store.get_node("material:ni") is not None  # shared entity still intact


def test_purge_unknown_source_deletes_nothing(store: KuzuGraphStore) -> None:
    _seed(store)
    out = purge_source(store, "doc:does-not-exist")
    assert out["deleted_nodes"] == 0
    assert store.counts()["nodes"] == 5  # nothing touched


def test_delete_source_nodes_returns_count(store: KuzuGraphStore) -> None:
    _seed(store)
    assert delete_source_nodes(store, _DOC) == 4
    assert delete_source_nodes(store, _DOC) == 0  # idempotent count-then-delete


# -- side stores (registry / vector) — §3/§4 ----------------------------------
class _FakeRegistry:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, source_id: str) -> None:
        self.deleted.append(source_id)


class _FakeVector:
    def __init__(self) -> None:
        self.purged: list[str] = []

    def delete_by_doc(self, doc_id: str) -> None:
        self.purged.append(doc_id)


class _BoomVector:
    def delete_by_doc(self, doc_id: str) -> None:  # deliberately fails
        raise RuntimeError("qdrant unavailable")


def test_purge_also_hits_registry_and_vector(store: KuzuGraphStore) -> None:
    _seed(store)
    reg, vec = _FakeRegistry(), _FakeVector()

    out = purge_source(store, _DOC, registry=reg, vector=vec)

    assert out == {
        "source_id": _DOC,
        "deleted_nodes": 4,
        "registry_deleted": True,
        "vector_purged": True,
    }
    assert reg.deleted == [_DOC]
    assert vec.purged == [_DOC]


def test_failing_vector_does_not_abort_graph_delete(store: KuzuGraphStore) -> None:
    _seed(store)
    reg = _FakeRegistry()

    # Vector store raises — must be swallowed (best-effort, §3) and the graph +
    # registry deletes must still complete.
    out = purge_source(store, _DOC, registry=reg, vector=_BoomVector())

    assert out["deleted_nodes"] == 4  # graph cascade ran despite the vector failure
    assert out["registry_deleted"] is True
    assert out["vector_purged"] is False
    assert reg.deleted == [_DOC]
    assert store.get_node(_DOC) is None
    assert store.get_node("material:ni") is not None
