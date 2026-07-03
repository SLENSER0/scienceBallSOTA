"""Tests for the Cytoscape.js layout catalog + recommender (§17.10)."""

from __future__ import annotations

from kg_retrievers.cytoscape_layout_catalog import (
    LayoutOption,
    get_layout,
    list_layouts,
    recommend_layout,
)


def test_catalog_includes_expected_layouts() -> None:
    names = {opt.name for opt in list_layouts()}
    for expected in ("cose-bilkent", "dagre", "cola", "circle", "concentric", "breadthfirst"):
        assert expected in names


def test_layout_names_are_unique() -> None:
    names = [opt.name for opt in list_layouts()]
    assert len(names) == len(set(names))


def test_cose_bilkent_present() -> None:
    assert get_layout("cose-bilkent") is not None


def test_dagre_is_directed() -> None:
    dagre = get_layout("dagre")
    assert dagre is not None
    assert dagre.directed is True


def test_get_missing_layout_returns_none() -> None:
    assert get_layout("missing") is None


def test_recommend_dag_returns_dagre() -> None:
    # is_dag wins even for a large graph.
    assert recommend_layout(50, 100, is_dag=True).name == "dagre"


def test_recommend_small_graph_returns_circle() -> None:
    assert recommend_layout(6, 4).name == "circle"


def test_recommend_small_graph_boundary_at_12() -> None:
    # node_count == 12 is still "small"; 13 tips over into the density branch.
    assert recommend_layout(12, 4).name == "circle"
    assert recommend_layout(13, 4).name == "cola"


def test_recommend_dense_graph_returns_cose_bilkent() -> None:
    # edge_count (500) > 2 * node_count (200) → dense.
    assert recommend_layout(100, 500).name == "cose-bilkent"


def test_recommend_default_returns_cola() -> None:
    # 120 edges is not > 2*100, and 100 nodes is not small → general case.
    assert recommend_layout(100, 120).name == "cola"


def test_recommend_dense_boundary_is_strict() -> None:
    # exactly 2 * node_count is NOT dense (strict >), so falls through to cola.
    assert recommend_layout(50, 100).name == "cola"
    assert recommend_layout(50, 101).name == "cose-bilkent"


def test_as_dict_round_trips_params() -> None:
    option = get_layout("dagre")
    assert option is not None
    d = option.as_dict()
    assert d["name"] == "dagre"
    assert d["directed"] is True
    assert d["params"] == option.params


def test_as_dict_params_is_a_copy() -> None:
    option = get_layout("cola")
    assert option is not None
    d = option.as_dict()
    d["params"]["edgeLength"] = 999
    # Mutating the dict copy must not touch the frozen catalog entry.
    assert option.params["edgeLength"] == 45


def test_layout_option_is_frozen() -> None:
    option = LayoutOption(name="x", label="X", best_for="test", directed=False, params={"a": 1})
    try:
        option.name = "y"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("LayoutOption should be frozen")
