"""Graph version diff — added / removed / changed (§16.10).

Pure-dict diff cases use hand-made snapshots with hand-checked expected deltas;
store cases seed a temp :class:`KuzuGraphStore`, edit it, and diff the snapshots.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_diff import (
    GraphDiff,
    diff_snapshots,
    diff_store_snapshots,
    edge_key,
    snapshot_store,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


@pytest.fixture
def store2():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g2"))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Pure-dict diff core
# ---------------------------------------------------------------------------
def test_diff_added_removed_changed() -> None:
    before = {
        "nodes": {
            "a": {"name": "Никель", "confidence": 0.9},  # will change
            "b": {"name": "Copper"},  # will be removed
        },
        "edges": {},
    }
    after = {
        "nodes": {
            "a": {"name": "Никель", "confidence": 0.5},  # confidence changed
            "c": {"name": "Cobalt"},  # added
        },
        "edges": {},
    }
    diff = diff_snapshots(before, after)

    assert diff.added_nodes == {"c": {"name": "Cobalt"}}
    assert diff.removed_nodes == {"b": {"name": "Copper"}}
    assert diff.changed_nodes == {"a": {"confidence": [0.9, 0.5]}}
    assert diff.node_change_count == 3
    assert not diff.is_empty


def test_no_change_yields_empty_diff() -> None:
    snap = {
        "nodes": {"a": {"name": "Никель", "verified": True}},
        "edges": {"a|APPLIES_TO|b": {"type": "APPLIES_TO"}},
    }
    diff = diff_snapshots(snap, dict(snap))  # identical content

    assert diff.is_empty
    assert diff.added_nodes == {}
    assert diff.removed_nodes == {}
    assert diff.changed_nodes == {}
    assert diff.added_edges == {}
    assert diff.removed_edges == {}


def test_changed_detects_single_field() -> None:
    before = {"nodes": {"m": {"name": "cd", "value_normalized": 250.0, "confidence": 0.8}}}
    after = {"nodes": {"m": {"name": "cd", "value_normalized": 300.0, "confidence": 0.8}}}
    diff = diff_snapshots(before, after)

    # only value_normalized differs; name and confidence are untouched
    assert diff.changed_nodes == {"m": {"value_normalized": [250.0, 300.0]}}
    assert diff.added_nodes == {}
    assert diff.removed_nodes == {}


def test_changed_field_absent_on_one_side_reads_as_none() -> None:
    before = {"nodes": {"x": {"name": "X"}}}
    after = {"nodes": {"x": {"name": "X", "review_status": "accepted"}}}
    diff = diff_snapshots(before, after)

    assert diff.changed_nodes == {"x": {"review_status": [None, "accepted"]}}


def test_edges_added_and_removed() -> None:
    before = {
        "nodes": {"a": {}, "b": {}, "c": {}},
        "edges": {
            "a|APPLIES_TO|b": {"type": "APPLIES_TO"},  # survives
            "a|ABOUT|c": {"type": "ABOUT"},  # removed
        },
    }
    after = {
        "nodes": {"a": {}, "b": {}, "c": {}},
        "edges": {
            "a|APPLIES_TO|b": {"type": "APPLIES_TO"},  # survives
            "b|SUPPORTED_BY|c": {"type": "SUPPORTED_BY"},  # added
        },
    }
    diff = diff_snapshots(before, after)

    assert diff.added_edges == {"b|SUPPORTED_BY|c": {"type": "SUPPORTED_BY"}}
    assert diff.removed_edges == {"a|ABOUT|c": {"type": "ABOUT"}}
    assert diff.edge_change_count == 2


def test_as_dict_shape() -> None:
    diff = diff_snapshots(
        {"nodes": {"a": {"name": "A"}}},
        {"nodes": {"a": {"name": "B"}}},
    )
    d = diff.as_dict()

    assert d["changed_nodes"] == {"a": {"name": ["A", "B"]}}
    assert d["is_empty"] is False
    assert d["node_change_count"] == 1
    assert set(d) == {
        "added_nodes",
        "removed_nodes",
        "changed_nodes",
        "added_edges",
        "removed_edges",
        "is_empty",
        "node_change_count",
        "edge_change_count",
    }
    assert isinstance(diff, GraphDiff)


# ---------------------------------------------------------------------------
# Store-backed snapshot + diff
# ---------------------------------------------------------------------------
def _seed(s: KuzuGraphStore) -> None:
    s.upsert_node("material:ni", "Material", name="Никель", confidence=0.9, formula="Ni")
    s.upsert_node("meas:cd", "Measurement", name="current density", value_normalized=250.0)
    s.upsert_edge("meas:cd", "material:ni", "ABOUT", confidence=0.8)


def test_snapshot_store_keeps_only_stable_fields(store: KuzuGraphStore) -> None:
    _seed(store)
    snap = snapshot_store(store)

    # 'formula' lives in props JSON and is NOT a stable comparable field -> excluded
    assert snap["nodes"]["material:ni"] == {"name": "Никель", "confidence": 0.9}
    assert "formula" not in snap["nodes"]["material:ni"]
    assert snap["nodes"]["meas:cd"] == {"name": "current density", "value_normalized": 250.0}
    assert edge_key("meas:cd", "ABOUT", "material:ni") in snap["edges"]


def test_snapshot_and_diff_over_edited_store(
    store: KuzuGraphStore,
    store2: KuzuGraphStore,
) -> None:
    _seed(store)  # before version
    _seed(store2)
    store2.upsert_node("material:ni", "Material", name="Никель", confidence=0.4)  # edit
    store2.upsert_node("material:co", "Material", name="Cobalt", confidence=0.7)  # add

    diff = diff_store_snapshots(store, store2)

    assert diff.changed_nodes == {"material:ni": {"confidence": [0.9, 0.4]}}
    assert diff.added_nodes == {"material:co": {"name": "Cobalt", "confidence": 0.7}}
    assert diff.removed_nodes == {}


def test_diff_store_edge_added_and_node_ids_scope(
    store: KuzuGraphStore,
    store2: KuzuGraphStore,
) -> None:
    _seed(store)
    _seed(store2)
    store2.upsert_node("meas:t", "Measurement", name="temp", value_normalized=60.0)
    store2.upsert_edge("meas:t", "material:ni", "ABOUT", confidence=0.5)

    # unscoped: sees the new node and the new edge
    full = diff_store_snapshots(store, store2)
    assert full.added_nodes == {"meas:t": {"name": "temp", "value_normalized": 60.0}}
    assert full.added_edges == {
        edge_key("meas:t", "ABOUT", "material:ni"): {
            "type": "ABOUT",
            "confidence": 0.5,
        }
    }

    # scoped to the two original ids: the new edge is out of scope (endpoint absent)
    scoped = diff_store_snapshots(store, store2, node_ids=["material:ni", "meas:cd"])
    assert scoped.is_empty
