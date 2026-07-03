"""Тесты дельты графа для ``POST /graph/diff`` (§14.6).

Hand-checkable tests for :mod:`api_gateway.graph_diff`: added/removed/changed
splits for nodes and edges, ``_before`` / ``_after`` capture, byte-identical
records excluded from every list, empty-vs-empty diff, the exact six list keys
plus counts of :meth:`GraphDiff.as_dict`, and keyed (non-positional) matching.
"""

from __future__ import annotations

from api_gateway.graph_diff import GraphDiff, diff_graphs


def test_node_only_in_after_is_added() -> None:
    """Узел только в after → added_nodes / added-only node (assertion 1)."""
    before = {"nodes": [], "edges": []}
    after = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
    diff = diff_graphs(before, after)
    assert diff.added_nodes == [{"id": "n1", "label": "A"}]
    assert diff.removed_nodes == []
    assert diff.changed_nodes == []


def test_node_only_in_before_is_removed() -> None:
    """Узел только в before → removed_nodes / removed-only node (assertion 2)."""
    before = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
    after = {"nodes": [], "edges": []}
    diff = diff_graphs(before, after)
    assert diff.removed_nodes == [{"id": "n1", "label": "A"}]
    assert diff.added_nodes == []
    assert diff.changed_nodes == []


def test_differing_confidence_is_changed_with_snapshots() -> None:
    """Разная confidence → changed с _before/_after / changed node (assertion 3)."""
    before = {"nodes": [{"id": "n1", "confidence": 0.5}], "edges": []}
    after = {"nodes": [{"id": "n1", "confidence": 0.9}], "edges": []}
    diff = diff_graphs(before, after)
    assert len(diff.changed_nodes) == 1
    entry = diff.changed_nodes[0]
    assert entry["id"] == "n1"
    assert entry["confidence"] == 0.9
    assert entry["_before"] == {"id": "n1", "confidence": 0.5}
    assert entry["_after"] == {"id": "n1", "confidence": 0.9}
    assert diff.added_nodes == []
    assert diff.removed_nodes == []


def test_byte_identical_node_in_no_list() -> None:
    """Идентичный узел не попадает ни в один список / unchanged (assertion 4)."""
    node = {"id": "n1", "label": "A", "confidence": 0.7}
    before = {"nodes": [dict(node)], "edges": []}
    after = {"nodes": [dict(node)], "edges": []}
    diff = diff_graphs(before, after)
    assert diff.added_nodes == []
    assert diff.removed_nodes == []
    assert diff.changed_nodes == []


def test_edges_follow_three_way_split() -> None:
    """Рёбра делятся так же: add/remove/change / edge split (assertion 5)."""
    before = {
        "nodes": [],
        "edges": [
            {"id": "e_rem", "type": "cites"},
            {"id": "e_chg", "weight": 1},
        ],
    }
    after = {
        "nodes": [],
        "edges": [
            {"id": "e_add", "type": "uses"},
            {"id": "e_chg", "weight": 2},
        ],
    }
    diff = diff_graphs(before, after)
    assert diff.added_edges == [{"id": "e_add", "type": "uses"}]
    assert diff.removed_edges == [{"id": "e_rem", "type": "cites"}]
    assert len(diff.changed_edges) == 1
    chg = diff.changed_edges[0]
    assert chg["id"] == "e_chg"
    assert chg["weight"] == 2
    assert chg["_before"] == {"id": "e_chg", "weight": 1}
    assert chg["_after"] == {"id": "e_chg", "weight": 2}


def test_empty_vs_empty_all_lists_empty() -> None:
    """Пустой→пустой: все списки пусты, added==0 / empty diff (assertion 6)."""
    diff = diff_graphs({"nodes": [], "edges": []}, {"nodes": [], "edges": []})
    assert diff.added_nodes == []
    assert diff.removed_nodes == []
    assert diff.changed_nodes == []
    assert diff.added_edges == []
    assert diff.removed_edges == []
    assert diff.changed_edges == []
    payload = diff.as_dict()
    assert payload["added"] == 0
    assert payload["removed"] == 0
    assert payload["changed"] == 0


def test_as_dict_exposes_exactly_six_list_keys() -> None:
    """as_dict раскрывает ровно шесть списков / list keys (assertion 7)."""
    diff = diff_graphs({"nodes": [], "edges": []}, {"nodes": [], "edges": []})
    payload = diff.as_dict()
    list_keys = {k for k, v in payload.items() if isinstance(v, list)}
    assert list_keys == {
        "added_nodes",
        "removed_nodes",
        "changed_nodes",
        "added_edges",
        "removed_edges",
        "changed_edges",
    }
    assert set(payload) - list_keys == {"added", "removed", "changed"}


def test_reordered_ids_match_by_key_not_position() -> None:
    """Переставленные id совпадают по ключу / keyed match (assertion 8)."""
    before = {
        "nodes": [{"id": "a", "v": 1}, {"id": "b", "v": 2}],
        "edges": [],
    }
    after = {
        "nodes": [{"id": "b", "v": 2}, {"id": "a", "v": 1}],
        "edges": [],
    }
    diff = diff_graphs(before, after)
    assert diff.added_nodes == []
    assert diff.removed_nodes == []
    assert diff.changed_nodes == []


def test_as_dict_counts_aggregate_nodes_and_edges() -> None:
    """Счётчики суммируют узлы и рёбра / counts aggregate both."""
    before = {"nodes": [{"id": "n_rem"}], "edges": [{"id": "e_chg", "w": 1}]}
    after = {
        "nodes": [{"id": "n_add"}],
        "edges": [{"id": "e_chg", "w": 2}],
    }
    diff = diff_graphs(before, after)
    payload = diff.as_dict()
    assert payload["added"] == 1
    assert payload["removed"] == 1
    assert payload["changed"] == 1


def test_graph_diff_is_frozen() -> None:
    """GraphDiff неизменяем / frozen dataclass rejects mutation."""
    diff = GraphDiff([], [], [], [], [], [])
    try:
        diff.added_nodes = [{"id": "x"}]  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("GraphDiff must be frozen")


def test_missing_nodes_edges_keys_default_empty() -> None:
    """Отсутствие nodes/edges трактуется как пусто / defaulted keys."""
    diff = diff_graphs({}, {"nodes": [{"id": "n1"}]})
    assert diff.added_nodes == [{"id": "n1"}]
    assert diff.removed_nodes == []
    assert diff.added_edges == []
