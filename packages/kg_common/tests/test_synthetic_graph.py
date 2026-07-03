"""Тесты фабрики синтетического графа (§23.3).

Hand-checkable assertions for the deterministic generator: exact counts,
evidence-first invariant, no dangling edges, seed stability/variation.
"""

from __future__ import annotations

from kg_common.testing.synthetic_graph import (
    SyntheticGraph,
    generate_graph,
    node_counts,
)


def test_material_count_exact() -> None:
    g = generate_graph(materials=10)
    assert node_counts(g)["Material"] == 10


def test_total_experiments_is_product() -> None:
    g = generate_graph(materials=5, experiments_per_material=3)
    assert node_counts(g)["Experiment"] == 5 * 3


def test_total_measurements_is_product() -> None:
    g = generate_graph(materials=4, experiments_per_material=2, measurements_per_experiment=3)
    assert node_counts(g)["Measurement"] == 4 * 2 * 3


def test_evidence_first_one_per_measurement() -> None:
    g = generate_graph(materials=6, experiments_per_material=2, measurements_per_experiment=2)
    counts = node_counts(g)
    assert counts["Evidence"] == counts["Measurement"]
    # Каждое измерение имеет ровно одно ребро SUPPORTED_BY на существующий Evidence.
    ev_ids = {n["id"] for n in g.nodes if n["label"] == "Evidence"}
    meas_ids = {n["id"] for n in g.nodes if n["label"] == "Measurement"}
    supported_by = [e for e in g.edges if e["label"] == "SUPPORTED_BY"]
    assert len(supported_by) == len(meas_ids)
    assert {e["source"] for e in supported_by} == meas_ids
    assert {e["target"] for e in supported_by} == ev_ids


def test_ids_deterministic_and_stable() -> None:
    a = generate_graph(materials=3, seed=7)
    b = generate_graph(materials=3, seed=7)
    assert a.as_dict() == b.as_dict()
    assert a.nodes[0]["id"] == "mat:000000"


def test_different_seed_changes_values_not_counts() -> None:
    a = generate_graph(materials=8, experiments_per_material=2, seed=0)
    b = generate_graph(materials=8, experiments_per_material=2, seed=1)
    assert a.counts == b.counts
    assert node_counts(a) == node_counts(b)
    # ids идентичны / ids identical across seeds.
    assert [n["id"] for n in a.nodes] == [n["id"] for n in b.nodes]
    # ...но хотя бы одно значение атрибута отличается / at least one value differs.
    a_vals = [n.get("temperature_c") for n in a.nodes if n["label"] == "Experiment"]
    b_vals = [n.get("temperature_c") for n in b.nodes if n["label"] == "Experiment"]
    assert a_vals != b_vals


def test_edges_reference_existing_nodes_no_dangling() -> None:
    g = generate_graph(materials=5, experiments_per_material=3, measurements_per_experiment=2)
    ids = {n["id"] for n in g.nodes}
    for e in g.edges:
        assert e["source"] in ids
        assert e["target"] in ids


def test_empty_graph_for_zero_materials() -> None:
    g = generate_graph(materials=0)
    assert g.nodes == ()
    assert g.edges == ()
    assert all(v == 0 for v in g.counts.values())
    assert node_counts(g) == g.counts


def test_counts_sum_to_number_of_nodes() -> None:
    g = generate_graph(materials=7, experiments_per_material=2, measurements_per_experiment=2)
    assert sum(g.counts.values()) == len(g.nodes)
    assert node_counts(g) == g.counts


def test_frozen_dataclass_and_as_dict_roundtrip() -> None:
    g = generate_graph(materials=2)
    assert isinstance(g, SyntheticGraph)
    d = g.as_dict()
    assert set(d) == {"nodes", "edges", "counts"}
    # as_dict возвращает копии / mutating the dict must not affect the frozen graph.
    d["nodes"].append({"id": "x", "label": "Material"})
    assert len(g.nodes) == sum(g.counts.values())


def test_expected_edge_labels_present() -> None:
    g = generate_graph(materials=2, experiments_per_material=1, measurements_per_experiment=1)
    labels = {e["label"] for e in g.edges}
    assert labels == {"HAS_EXPERIMENT", "MEASURED", "SUPPORTED_BY"}
