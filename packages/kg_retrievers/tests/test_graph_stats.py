"""Tests for §8.13 graph statistics over a KuzuGraphStore.

Each test builds a fresh temp store and asserts concrete, hand-checked values.

Hand-checkable seed (see ``_seed``): 5 nodes, 4 directed edges.

- labels: Material×2, ProcessingRegime×1, Measurement×1, Evidence×1;
- rel types: APPLIES_TO×2, ABOUT_REGIME×1, SUPPORTED_BY×1;
- avg_degree = 2·E / N = 2·4 / 5 = 1.6;
- density = E / (N·(N − 1)) = 4 / (5·4) = 0.2.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.graph_stats import graph_stats
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KuzuGraphStore]:
    """Fresh embedded store (schema created, no nodes yet)."""
    s = KuzuGraphStore(str(tmp_path / "g"))
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    """5 nodes / 4 edges with duplicate labels and rel types (see module docstring)."""
    s.upsert_node("m:1", "Material", name="Никель", canonical_name="nickel")
    s.upsert_node("m:2", "Material", name="Медь", canonical_name="copper")
    s.upsert_node("r:1", "ProcessingRegime", name="electrowinning", temperature_c=60.0)
    s.upsert_node("meas:1", "Measurement", property_name="current_density", value_normalized=250.0)
    s.upsert_node("ev:1", "Evidence", text="плотность тока 250 А/м²", doc_id="doc:x")
    s.upsert_edge("r:1", "m:1", "APPLIES_TO", confidence=0.9)
    s.upsert_edge("r:1", "m:2", "APPLIES_TO", confidence=0.8)
    s.upsert_edge("meas:1", "r:1", "ABOUT_REGIME", confidence=0.7)
    s.upsert_edge("meas:1", "ev:1", "SUPPORTED_BY", confidence=1.0, evidence_ids=["ev:1"])


def test_node_and_edge_counts(store: KuzuGraphStore) -> None:
    _seed(store)
    st = graph_stats(store)
    assert st.n_nodes == 5
    assert st.n_edges == 4


def test_by_label(store: KuzuGraphStore) -> None:
    _seed(store)
    st = graph_stats(store)
    assert st.by_label == {"Material": 2, "ProcessingRegime": 1, "Measurement": 1, "Evidence": 1}


def test_by_rel_type(store: KuzuGraphStore) -> None:
    _seed(store)
    st = graph_stats(store)
    assert st.by_rel_type == {"APPLIES_TO": 2, "ABOUT_REGIME": 1, "SUPPORTED_BY": 1}


def test_avg_degree(store: KuzuGraphStore) -> None:
    _seed(store)
    st = graph_stats(store)
    assert st.avg_degree == 1.6  # 2 * 4 edges / 5 nodes


def test_density(store: KuzuGraphStore) -> None:
    _seed(store)
    st = graph_stats(store)
    assert st.density == 0.2  # 4 edges / (5 * 4)


def test_empty_store_zeros(store: KuzuGraphStore) -> None:
    st = graph_stats(store)
    assert st.n_nodes == 0
    assert st.n_edges == 0
    assert st.by_label == {}
    assert st.by_rel_type == {}
    assert st.avg_degree == 0.0
    assert st.density == 0.0


def test_as_dict(store: KuzuGraphStore) -> None:
    _seed(store)
    st = graph_stats(store)
    assert st.as_dict() == {
        "n_nodes": 5,
        "n_edges": 4,
        "by_label": {"Material": 2, "ProcessingRegime": 1, "Measurement": 1, "Evidence": 1},
        "by_rel_type": {"APPLIES_TO": 2, "ABOUT_REGIME": 1, "SUPPORTED_BY": 1},
        "avg_degree": 1.6,
        "density": 0.2,
    }


def test_stats_is_frozen(store: KuzuGraphStore) -> None:
    st = graph_stats(store)
    with pytest.raises(FrozenInstanceError):
        st.n_nodes = 99  # type: ignore[misc]
