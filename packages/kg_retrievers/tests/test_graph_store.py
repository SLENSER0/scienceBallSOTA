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
