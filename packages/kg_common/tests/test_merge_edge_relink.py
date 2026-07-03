"""Tests for the §16.6 merge edge relink & dedup planner (RU/EN).

Каждый тест — ручная проверка (hand-checkable): маленький набор рёбер, явный
ожидаемый результат. No Kuzu required — relink_edges is a pure planner.
"""

from __future__ import annotations

from kg_common.storage.merge_edge_relink import RelinkPlan, edge_key, relink_edges


def _edge(src: str, rel_type: str, dst: str) -> dict:
    return {"src": src, "rel_type": rel_type, "dst": dst}


def test_relink_rewrites_src_to_canonical() -> None:
    """(1) (drop1)-KNOWS->(x) becomes (canon)-KNOWS->(x) in kept_edges."""
    plan = relink_edges([_edge("drop1", "KNOWS", "x")], {"drop1"}, "canon")
    assert plan.kept_edges == [_edge("canon", "KNOWS", "x")]
    assert plan.dropped_edges == []
    assert plan.self_loops_removed == 0
    assert plan.duplicates_collapsed == 0


def test_relink_drops_new_self_loop() -> None:
    """(2) (drop1)-KNOWS->(canon) collapses to a self-loop and is removed."""
    plan = relink_edges([_edge("drop1", "KNOWS", "canon")], {"drop1"}, "canon")
    assert plan.kept_edges == []
    assert plan.self_loops_removed == 1
    assert plan.dropped_edges == [_edge("canon", "KNOWS", "canon")]


def test_relink_collapses_parallel_duplicates() -> None:
    """(3) two sources rewriting to the same (canon,REL,x) collapse to one."""
    edges = [_edge("drop1", "REL", "x"), _edge("drop2", "REL", "x")]
    plan = relink_edges(edges, {"drop1", "drop2"}, "canon")
    assert plan.kept_edges == [_edge("canon", "REL", "x")]
    assert plan.duplicates_collapsed == 1
    assert plan.dropped_edges == [_edge("canon", "REL", "x")]


def test_relink_passes_unrelated_edge_unchanged() -> None:
    """(4) an unrelated edge (a)-R->(b) passes through unchanged."""
    plan = relink_edges([_edge("a", "R", "b")], {"drop1"}, "canon")
    assert plan.kept_edges == [_edge("a", "R", "b")]
    assert plan.self_loops_removed == 0
    assert plan.duplicates_collapsed == 0


def test_relink_keeps_preexisting_self_loop() -> None:
    """(5) a pre-existing self-loop rewrites but is NOT counted as removed."""
    plan = relink_edges([_edge("drop1", "R", "drop1")], {"drop1"}, "canon")
    assert plan.kept_edges == [_edge("canon", "R", "canon")]
    assert plan.self_loops_removed == 0
    assert plan.dropped_edges == []


def test_as_dict_kept_length_equals_unique_keys() -> None:
    """(6) as_dict()['kept_edges'] length equals number of unique kept keys."""
    edges = [
        _edge("drop1", "REL", "x"),  # -> (canon,REL,x)
        _edge("drop2", "REL", "x"),  # duplicate of above -> collapsed
        _edge("a", "R", "b"),  # unrelated
        _edge("drop1", "KNOWS", "canon"),  # -> self-loop, removed
    ]
    plan = relink_edges(edges, {"drop1", "drop2"}, "canon")
    d = plan.as_dict()
    unique_keys = {edge_key(e) for e in d["kept_edges"]}
    assert len(d["kept_edges"]) == len(unique_keys)
    assert len(d["kept_edges"]) == 2
    assert d["duplicates_collapsed"] == 1
    assert d["self_loops_removed"] == 1


def test_empty_edges_yield_empty_plan() -> None:
    """(7) empty edges → empty plan with zero counters."""
    plan = relink_edges([], {"drop1"}, "canon")
    assert isinstance(plan, RelinkPlan)
    assert plan.kept_edges == []
    assert plan.dropped_edges == []
    assert plan.self_loops_removed == 0
    assert plan.duplicates_collapsed == 0
    assert plan.as_dict() == {
        "kept_edges": [],
        "dropped_edges": [],
        "self_loops_removed": 0,
        "duplicates_collapsed": 0,
    }
