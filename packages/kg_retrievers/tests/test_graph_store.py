"""KuzuGraphStore: upsert idempotency, numeric filters, traversal, payload."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _seed_small(s: KuzuGraphStore) -> None:
    s.upsert_node(
        "material:ni",
        "Material",
        name="Никель",
        canonical_name="nickel",
        aliases_text="nickel|никель|Ni",
        confidence=1.0,
    )
    s.upsert_node(
        "regime:ew",
        "ProcessingRegime",
        name="electrowinning 60C",
        operation="electrowinning",
        temperature_c=60.0,
        confidence=0.9,
    )
    s.upsert_node(
        "meas:cd",
        "Measurement",
        name="current density",
        property_name="current_density",
        value_normalized=250.0,
        normalized_unit="A/m2",
        confidence=0.85,
    )
    s.upsert_node("ev:1", "Evidence", text="плотность тока 250 А/м²", doc_id="doc:x", page=3)
    s.upsert_edge("meas:cd", "regime:ew", "ABOUT_REGIME", confidence=0.9)
    s.upsert_edge("regime:ew", "material:ni", "APPLIES_TO", confidence=0.8)
    s.upsert_edge("meas:cd", "ev:1", "SUPPORTED_BY", confidence=1.0, evidence_ids=["ev:1"])


def test_upsert_idempotent(store: KuzuGraphStore) -> None:
    _seed_small(store)
    _seed_small(store)  # run twice
    c = store.counts()
    assert c["nodes"] == 4
    assert c["rels"] == 3


def test_props_roundtrip(store: KuzuGraphStore) -> None:
    store.upsert_node("material:cu", "Material", name="Copper", custom_field="xyz", formula="Cu")
    nd = store.get_node("material:cu")
    assert nd is not None
    assert nd["name"] == "Copper"
    assert nd["custom_field"] == "xyz"  # came back from props JSON
    assert nd["formula"] == "Cu"


def test_numeric_range_filter(store: KuzuGraphStore) -> None:
    _seed_small(store)
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label='Measurement' AND n.value_normalized >= $lo "
        "AND n.value_normalized <= $hi RETURN n.id",
        {"lo": 200.0, "hi": 300.0},
    )
    assert [r[0] for r in rows] == ["meas:cd"]


def test_neighbors_payload(store: KuzuGraphStore) -> None:
    _seed_small(store)
    resp = store.neighbors("regime:ew", depth=2)
    ids = {n.id for n in resp.nodes}
    assert {"regime:ew", "material:ni", "meas:cd"} <= ids
    assert any(e.type == "APPLIES_TO" for e in resp.edges)


def test_counts_by_label(store: KuzuGraphStore) -> None:
    _seed_small(store)
    by = store.counts_by_label()
    assert by.get("Material") == 1
    assert by.get("Evidence") == 1


def test_upsert_ignores_id_prop(store: KuzuGraphStore) -> None:
    # passing 'id' as a prop must not crash (Kuzu rejects PK-SET) — finding graph_store:132
    store.upsert_node("material:x", "Material", id="OTHER", name="X")
    nd = store.get_node("material:x")
    assert nd is not None and nd["id"] == "material:x" and nd["name"] == "X"
    assert store.get_node("OTHER") is None


def test_upsert_node_guarded_protects_reviewed(store: KuzuGraphStore) -> None:
    store.upsert_node("material:r", "Material", name="orig", review_status="accepted")
    assert store.upsert_node_guarded("material:r", "Material", name="changed") is False
    assert store.get_node("material:r")["name"] == "orig"


# -- batched hydration (get_nodes / subgraph_from_ids) — N+1 -> 1 query ---------
def test_get_nodes_matches_get_node_loop(store: KuzuGraphStore) -> None:
    """Batched get_nodes() returns exactly what a per-id get_node() loop would."""
    _seed_small(store)
    ids = ["material:ni", "regime:ew", "meas:cd", "ev:1", "missing:x"]
    batched = store.get_nodes(ids)
    per_id = {nid: nd for nid in ids if (nd := store.get_node(nid)) is not None}
    assert batched == per_id
    assert "missing:x" not in batched  # non-existent id skipped, like get_node -> None
    assert store.get_nodes([]) == {}  # empty ids -> no query, empty dict


def test_subgraph_from_ids_hydration_equivalent(store: KuzuGraphStore) -> None:
    """subgraph_from_ids nodes are identical to the old get_node-per-id hydration."""
    _seed_small(store)
    resp = store.subgraph_from_ids(["meas:cd"], expand=2)
    got_ids = {n.id for n in resp.nodes}
    assert {"meas:cd", "regime:ew", "material:ni", "ev:1"} <= got_ids
    # Each hydrated DTO equals node_to_dto(get_node(id)) — the pre-batch code path.
    for n in resp.nodes:
        nd = store.get_node(n.id)
        assert nd is not None
        assert store.node_to_dto(nd) == n
    # A non-existent seed id is silently dropped (as get_node -> None was).
    resp2 = store.subgraph_from_ids(["meas:cd", "ghost:404"], expand=0)
    assert "ghost:404" not in {n.id for n in resp2.nodes}


# -- is_empty() cheap existence probe ------------------------------------------
def test_is_empty(store: KuzuGraphStore) -> None:
    assert store.is_empty() is True
    store.upsert_node("m:1", "Material", name="x")
    assert store.is_empty() is False
    # agrees with counts()['nodes'] == 0 (the decision it replaces at startup)
    assert store.is_empty() == (store.counts()["nodes"] == 0)


# -- read concurrency (dedicated read-connection pool) -------------------------
def test_in_batch_read_sees_uncommitted_writes(store: KuzuGraphStore) -> None:
    """Reads on the batch's own thread still see its uncommitted writes (unchanged)."""
    with store.batch():
        store.upsert_node("b:1", "Material", name="in-batch")
        assert store.get_node("b:1") is not None  # routed to write conn inside batch
        assert store.rows("MATCH (n:Node {id:'b:1'}) RETURN n.name")[0][0] == "in-batch"
    assert store.get_node("b:1")["name"] == "in-batch"  # visible after commit too


def test_concurrent_reads_return_correct_results(store: KuzuGraphStore) -> None:
    """Many threads reading at once (pool < threads) never error or corrupt rows."""
    import threading

    _seed_small(store)
    counts: list[int] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(15):
                counts.append(len(store.rows("MATCH (n:Node) RETURN n.id")))
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "read threads hung"
    assert not errors, errors
    assert counts and all(c == 4 for c in counts)


def test_read_from_other_thread_during_batch_does_not_block(store: KuzuGraphStore) -> None:
    """A read on another thread must not serialize behind an open write batch.

    Pre-optimization every read took the single write lock, so this read would
    have blocked until COMMIT and this test would deadlock. With the read pool it
    proceeds over Kuzu's MVCC snapshot, seeing only committed state.
    """
    import threading

    _seed_small(store)
    started = threading.Event()
    read_done = threading.Event()
    read_count: list[int] = []
    read_err: list[Exception] = []

    def reader() -> None:
        started.wait(5)
        try:
            read_count.append(len(store.rows("MATCH (n:Node) RETURN n.id")))
        except Exception as e:  # pragma: no cover - failure path
            read_err.append(e)
        finally:
            read_done.set()

    t = threading.Thread(target=reader)
    t.start()
    with store.batch():
        store.upsert_node("batch:new", "Material", name="uncommitted")
        started.set()
        assert read_done.wait(15), "reader blocked behind the open write transaction"
    t.join(timeout=5)
    assert not read_err, read_err
    assert read_count == [4]  # committed snapshot only — not the uncommitted node
