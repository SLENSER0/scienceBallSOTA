"""Reagraph-formatted graph diff — status-tagged node/edge lists (§16.10).

Hand-made :class:`GraphDiff` instances with hand-checked expected Reagraph output; one
case also drives the diff off a live temp :class:`KuzuGraphStore` end-to-end.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_diff import GraphDiff, diff_store_snapshots, edge_key
from kg_retrievers.graph_diff_reagraph import ReagraphDiff, to_reagraph
from kg_retrievers.graph_store import KuzuGraphStore


def _diff(**kw: object) -> GraphDiff:
    """Build a GraphDiff with empty defaults, overriding only the given buckets."""
    base: dict[str, dict] = {
        "added_nodes": {},
        "removed_nodes": {},
        "changed_nodes": {},
        "added_edges": {},
        "removed_edges": {},
    }
    base.update(kw)  # type: ignore[arg-type]
    return GraphDiff(**base)  # type: ignore[arg-type]


def test_added_node_status() -> None:
    """(1) A diff with one added node yields one node entry tagged ``added``."""
    rg = to_reagraph(_diff(added_nodes={"m1": {"name": "Steel"}}))
    assert len(rg.nodes) == 1
    assert rg.nodes[0]["id"] == "m1"
    assert rg.nodes[0]["status"] == "added"
    assert rg.nodes[0]["data"] == {"name": "Steel"}


def test_changed_node_carries_changes() -> None:
    """(2)/(4) Changed node -> status ``changed``, data['changes'] and count match."""
    rg = to_reagraph(_diff(changed_nodes={"m1": {"value": [1, 2]}}))
    assert len(rg.nodes) == 1
    node = rg.nodes[0]
    assert node["status"] == "changed"
    assert node["data"]["changes"] == {"value": [1, 2]}
    assert rg.counts["changed_nodes"] == 1


def test_removed_edge_status() -> None:
    """(3) A removed edge yields exactly one edge dict tagged ``removed``."""
    rg = to_reagraph(_diff(removed_edges={"a|R|b": {"type": "R"}}))
    assert len(rg.edges) == 1
    assert rg.edges[0]["id"] == "a|R|b"
    assert rg.edges[0]["status"] == "removed"
    assert rg.counts["removed_edges"] == 1


def test_empty_diff() -> None:
    """(5) An empty diff -> no nodes, no edges, every count zero."""
    rg = to_reagraph(_diff())
    assert rg.nodes == ()
    assert rg.edges == ()
    assert set(rg.counts) == {
        "added_nodes",
        "removed_nodes",
        "changed_nodes",
        "added_edges",
        "removed_edges",
    }
    assert all(v == 0 for v in rg.counts.values())


def test_node_ids_unique() -> None:
    """(6) Ids stay unique across added / removed / changed buckets."""
    rg = to_reagraph(
        _diff(
            added_nodes={"a": {"name": "A"}},
            removed_nodes={"b": {"name": "B"}},
            changed_nodes={"c": {"name": ["C", "C2"]}},
        )
    )
    ids = [n["id"] for n in rg.nodes]
    assert ids == ["a", "b", "c"]
    assert len(ids) == len(set(ids))


def test_as_dict_counts_is_plain_dict() -> None:
    """(7) ``as_dict()['counts']`` is a plain ``dict`` and round-trips the totals."""
    rg = to_reagraph(_diff(added_nodes={"m1": {"name": "Steel"}}))
    d = rg.as_dict()
    assert type(d["counts"]) is dict
    assert d["counts"]["added_nodes"] == 1
    assert isinstance(d["nodes"], list) and d["nodes"][0]["status"] == "added"


def test_accepts_mapping_form() -> None:
    """A ``GraphDiff.as_dict()`` mapping formats identically to the dataclass."""
    gd = _diff(added_nodes={"m1": {"name": "Steel"}}, removed_edges={"a|R|b": {"type": "R"}})
    from_obj = to_reagraph(gd)
    from_map = to_reagraph(gd.as_dict())
    assert from_obj.as_dict() == from_map.as_dict()


def test_from_live_store_diff() -> None:
    """End-to-end: diff two temp stores, then format the delta for Reagraph."""
    d1 = tempfile.mkdtemp()
    d2 = tempfile.mkdtemp()
    before = KuzuGraphStore(str(Path(d1) / "g"))
    after = KuzuGraphStore(str(Path(d2) / "g"))
    try:
        # both: n1, n2 present.
        for s in (before, after):
            s.upsert_node("n2", "Material", name="Beta")
        # before: n1 verified=False, edge n1 -> n2.
        before.upsert_node("n1", "Material", name="Alpha", verified=False)
        before.upsert_edge("n1", "n2", "REL")
        # after: n1 flipped verified, n3 added, edge dropped.
        after.upsert_node("n1", "Material", name="Alpha", verified=True)
        after.upsert_node("n3", "Material", name="Gamma")

        diff = diff_store_snapshots(before, after)
        rg = to_reagraph(diff)

        assert isinstance(rg, ReagraphDiff)
        by_id = {n["id"]: n for n in rg.nodes}
        assert by_id["n1"]["status"] == "changed"
        assert by_id["n1"]["data"]["changes"]["verified"] == [False, True]
        assert by_id["n3"]["status"] == "added"
        removed = [e for e in rg.edges if e["status"] == "removed"]
        assert removed and removed[0]["id"] == edge_key("n1", "REL", "n2")
        assert rg.counts["changed_nodes"] == 1
        assert rg.counts["removed_edges"] == 1
    finally:
        before.close()
        after.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
