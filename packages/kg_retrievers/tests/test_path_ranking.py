"""Graph-path ranking over hand-built paths (§8.14, pure python).

All values checkable by hand against the §8.14 formula::

    score = 0.5 * 1/(1 + length) + 0.5 * evidence/(1 + evidence)   # length = edges
    length = len(nodes) - 1

Four reference paths (rounded to 6 digits):

- P_SHORT  nodes [x, y]     len 1, ev 1 -> 0.5*0.5      + 0.5*0.5   = 0.5
- P_LONG   nodes [x, m, y]  len 2, ev 1 -> 0.5*(1/3)    + 0.5*0.5   = 0.416667
- P_RICH   nodes [x, y]     len 1, ev 3 -> 0.5*0.5      + 0.5*0.75  = 0.625
- P_POOR   nodes [x, y]     len 1, ev 0 -> 0.5*0.5      + 0.5*0.0   = 0.25

Ranked best-first: P_RICH (0.625) > P_SHORT (0.5) > P_LONG (0.416667) > P_POOR (0.25).
"""

from __future__ import annotations

from typing import Any

import pytest

from kg_retrievers.path_ranking import RankedPath, best_path, rank_paths

P_SHORT: dict[str, Any] = {"nodes": ["x", "y"], "evidence": ["e1"]}
P_LONG: dict[str, Any] = {"nodes": ["x", "m", "y"], "evidence": ["e1"]}
P_RICH: dict[str, Any] = {"nodes": ["x", "y"], "evidence": ["e1", "e2", "e3"]}
P_POOR: dict[str, Any] = {"nodes": ["x", "y"], "evidence": []}


def test_shorter_path_ranks_higher() -> None:
    # Same evidence (1), different length: the 1-edge path beats the 2-edge path.
    ranked = rank_paths([P_LONG, P_SHORT])
    assert [p.nodes for p in ranked] == [("x", "y"), ("x", "m", "y")]
    assert ranked[0].score == pytest.approx(0.5)
    assert ranked[1].score == pytest.approx(0.416667)
    assert ranked[0].score > ranked[1].score


def test_more_evidence_ranks_higher() -> None:
    # Same length (1 edge), different evidence: 3 evidence beats 1 beats 0.
    ranked = rank_paths([P_POOR, P_SHORT, P_RICH])
    assert [p.evidence_count for p in ranked] == [3, 1, 0]
    assert [p.score for p in ranked] == pytest.approx([0.625, 0.5, 0.25])
    assert ranked[0].score > ranked[1].score > ranked[2].score


def test_best_path_returns_top() -> None:
    # best_path == first of the full ranking (P_RICH, the highest score).
    top = best_path([P_SHORT, P_LONG, P_RICH, P_POOR])
    assert top is not None
    assert top.nodes == ("x", "y")
    assert top.evidence_count == 3
    assert top.score == pytest.approx(0.625)
    assert top == rank_paths([P_SHORT, P_LONG, P_RICH, P_POOR])[0]


def test_single_path() -> None:
    ranked = rank_paths([P_SHORT])
    assert len(ranked) == 1
    assert ranked[0].nodes == ("x", "y")
    assert ranked[0].length == 1
    assert ranked[0].evidence_count == 1
    assert ranked[0].score == pytest.approx(0.5)
    assert best_path([P_SHORT]) == ranked[0]


def test_empty_returns_empty() -> None:
    assert rank_paths([]) == []
    assert best_path([]) is None


def test_score_in_unit_interval() -> None:
    # A wide spread of paths, including degenerate ones, all stay within [0, 1].
    paths: list[dict[str, Any]] = [
        P_SHORT,
        P_LONG,
        P_RICH,
        P_POOR,
        {"nodes": ["only"], "evidence_count": 0},  # 1 node -> length 0
        {"nodes": [], "evidence": []},  # empty path -> length 0
        {"nodes": ["a", "b", "c", "d"], "evidence_count": 100},  # long + very rich
    ]
    for p in rank_paths(paths):
        assert 0.0 <= p.score <= 1.0


def test_as_dict_shape() -> None:
    d = best_path([P_SHORT, P_RICH]).as_dict()  # type: ignore[union-attr]
    assert set(d) == {"nodes", "length", "score", "evidence_count"}
    assert d["nodes"] == ["x", "y"]  # list, not tuple, for JSON
    assert d["length"] == 1
    assert d["evidence_count"] == 3
    assert d["score"] == pytest.approx(0.625)


def test_length_is_edge_count() -> None:
    # length is edges = nodes - 1, floored at 0 for single/empty node lists.
    ranked = rank_paths(
        [
            {"nodes": ["a", "b", "c"], "evidence": []},
            {"nodes": ["solo"], "evidence": []},
            {"nodes": [], "evidence": []},
        ]
    )
    by_nodes = {p.nodes: p.length for p in ranked}
    assert by_nodes[("a", "b", "c")] == 2
    assert by_nodes[("solo",)] == 0
    assert by_nodes[()] == 0


def test_explicit_evidence_count_wins() -> None:
    # explicit evidence_count overrides any evidence collection present.
    ranked = rank_paths([{"nodes": ["a", "b", "c"], "evidence_count": 5, "evidence": ["x"]}])
    p = ranked[0]
    assert p.evidence_count == 5
    assert p.length == 2
    # 0.5*(1/3) + 0.5*(5/6) = 0.166667 + 0.416667 = 0.583333
    assert p.score == pytest.approx(0.583333)


def test_ranked_path_is_frozen() -> None:
    p = rank_paths([P_SHORT])[0]
    assert isinstance(p, RankedPath)
    with pytest.raises((AttributeError, TypeError)):
        p.score = 0.0  # type: ignore[misc]


def test_tie_break_is_deterministic() -> None:
    # Two paths with identical score (same len 1, same ev 1) order by nodes tuple.
    a: dict[str, Any] = {"nodes": ["b", "z"], "evidence": ["e"]}
    b: dict[str, Any] = {"nodes": ["a", "z"], "evidence": ["e"]}
    forward = [p.nodes for p in rank_paths([a, b])]
    backward = [p.nodes for p in rank_paths([b, a])]
    assert forward == backward == [("a", "z"), ("b", "z")]
