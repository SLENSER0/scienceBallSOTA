"""Tests for Pajek ``.net`` network export (§22).

Ручные, hand-checkable проверки чистого stdlib-сериализатора: build_network /
to_pajek / PajekNetwork.as_dict.
"""

from __future__ import annotations

from kg_retrievers.graph_pajek_export import (
    PajekNetwork,
    build_network,
    to_pajek,
)


def test_empty_nodes_starts_vertices_zero() -> None:
    """Пустые узлы → to_pajek начинается с ``*Vertices 0``."""
    net = build_network([], [])
    text = to_pajek(net)
    assert text.startswith("*Vertices 0")


def test_two_nodes_get_ids_and_label_lines() -> None:
    """Узлы A,B получают id 1,2 и строки меток ``1 "A"`` / ``2 "B"``."""
    net = build_network([{"id": "A"}, {"id": "B"}], [])
    assert net.vertices == ((1, "A"), (2, "B"))
    text = to_pajek(net)
    assert '1 "A"' in text
    assert '2 "B"' in text


def test_directed_edge_yields_arc_line() -> None:
    """Ребро A->B даёт строку arc ``1 2 1.0`` под заголовком ``*Arcs``."""
    net = build_network([{"id": "A"}, {"id": "B"}], [{"source": "A", "target": "B"}])
    assert net.arcs == ((1, 2, 1.0),)
    text = to_pajek(net)
    assert "*Arcs" in text
    lines = text.splitlines()
    arcs_idx = lines.index("*Arcs")
    assert "1 2 1.0" in lines[arcs_idx + 1 :]


def test_undirected_emits_edges_header() -> None:
    """directed=False эмитит ``*Edges``, а не ``*Arcs``."""
    net = build_network(
        [{"id": "A"}, {"id": "B"}],
        [{"source": "A", "target": "B"}],
        directed=False,
    )
    text = to_pajek(net)
    assert "*Edges" in text
    assert "*Arcs" not in text


def test_edge_to_missing_node_is_dropped() -> None:
    """Ребро на отсутствующий узел пропускается, а не роняет экспорт."""
    net = build_network(
        [{"id": "A"}],
        [{"source": "A", "target": "GHOST"}, {"source": "NOPE", "target": "A"}],
    )
    assert net.arcs == ()
    text = to_pajek(net)  # не падает / does not crash
    assert text.startswith("*Vertices 1")


def test_custom_weight_key_renders_weight() -> None:
    """weight_key='w' с ребром {w:2.5} рендерит ``1 2 2.5``."""
    net = build_network(
        [{"id": "A"}, {"id": "B"}],
        [{"source": "A", "target": "B", "w": 2.5}],
        weight_key="w",
    )
    assert net.arcs == ((1, 2, 2.5),)
    text = to_pajek(net)
    lines = text.splitlines()
    arcs_idx = lines.index("*Arcs")
    assert "1 2 2.5" in lines[arcs_idx + 1 :]


def test_id_map_stable_across_two_calls() -> None:
    """build_network присваивает id стабильно между двумя вызовами."""
    nodes = [{"id": "X"}, {"id": "Y"}, {"id": "Z"}]
    net1 = build_network(nodes, [])
    net2 = build_network(nodes, [])
    assert net1.vertices == net2.vertices
    assert net1.vertices == ((1, "X"), (2, "Y"), (3, "Z"))


def test_as_dict_round_trips_directed_flag() -> None:
    """as_dict()['directed'] возвращает флаг обоих значений."""
    directed_net = PajekNetwork(vertices=(), arcs=(), directed=True)
    undirected_net = PajekNetwork(vertices=(), arcs=(), directed=False)
    assert directed_net.as_dict()["directed"] is True
    assert undirected_net.as_dict()["directed"] is False


def test_as_dict_shapes_vertices_and_arcs_as_lists() -> None:
    """as_dict() приводит кортежи vertices/arcs к спискам (list)."""
    net = build_network([{"id": "A"}, {"id": "B"}], [{"source": "A", "target": "B"}])
    d = net.as_dict()
    assert d["vertices"] == [[1, "A"], [2, "B"]]
    assert d["arcs"] == [[1, 2, 1.0]]


def test_duplicate_node_id_kept_once() -> None:
    """Повторный ``id`` не создаёт вторую вершину."""
    net = build_network([{"id": "A"}, {"id": "A"}, {"id": "B"}], [])
    assert net.vertices == ((1, "A"), (2, "B"))
