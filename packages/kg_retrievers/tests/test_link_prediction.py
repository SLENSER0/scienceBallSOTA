"""Локальное предсказание связей над Kuzu (§12.8). Local link prediction tests.

Each assertion is hand-checkable from the tiny undirected graph built in
``_build``: common neighbours, Jaccard, Adamic/Adar (1/log(deg)), resource
allocation (1/deg), preferential attachment (deg·deg) and candidate ranking.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.link_prediction import (
    LinkScore,
    _neighbors,
    rank_candidates,
    score_pair,
)


def _edge(s: KuzuGraphStore, x: str, y: str) -> None:
    s.upsert_node(x, "Material")
    s.upsert_node(y, "Material")
    s.upsert_edge(x, y, "RELATED", confidence=1.0)


def _build(s: KuzuGraphStore) -> None:
    # -- pair P,Q sharing exactly two neighbours s1,s2 (common == 2) --
    for other in ("P", "Q"):
        _edge(s, other, "s1")
        _edge(s, other, "s2")

    # -- pair A,B with neighbour sets {x,y} and {y,z} (jaccard == 1/3) --
    _edge(s, "A", "x")
    _edge(s, "A", "y")
    _edge(s, "B", "y")
    _edge(s, "B", "z")

    # -- pair C,D with disjoint neighbours (jaccard == 0, adamic_adar == 0) --
    _edge(s, "C", "c1")
    _edge(s, "D", "d1")

    # -- pair u,v whose only shared neighbour z2 has degree exactly 2 --
    #    deg(u)=deg(v)=2 → preferential = 4; z2 → adamic_adar 1/log(2), RA 0.5
    _edge(s, "u", "z2")
    _edge(s, "v", "z2")
    _edge(s, "u", "u1")
    _edge(s, "v", "v1")

    # -- ranking: seed S; strong SC shares 3 neighbours, weak WC shares none --
    for n in ("n1", "n2", "n3"):
        _edge(s, "S", n)
        _edge(s, "SC", n)
    _edge(s, "WC", "w1")


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


def test_neighbors_are_distinct_and_exclude_self(store: KuzuGraphStore) -> None:
    assert _neighbors(store, "A") == {"x", "y"}
    assert "A" not in _neighbors(store, "A")


def test_common_two_shared_neighbors(store: KuzuGraphStore) -> None:
    assert score_pair(store, "P", "Q").common == 2


def test_jaccard_one_third(store: KuzuGraphStore) -> None:
    # Na={x,y}, Nb={y,z}: |∩|=1, |∪|=3
    assert score_pair(store, "A", "B").jaccard == pytest.approx(1.0 / 3.0)


def test_no_common_neighbor_zeroes(store: KuzuGraphStore) -> None:
    sc = score_pair(store, "C", "D")
    assert sc.jaccard == 0.0
    assert sc.adamic_adar == 0.0


def test_adamic_adar_degree_two_neighbor(store: KuzuGraphStore) -> None:
    # only shared neighbour z2 has degree 2 → 1/log(2)
    assert score_pair(store, "u", "v").adamic_adar == pytest.approx(1.0 / math.log(2))


def test_resource_allocation_degree_two_neighbor(store: KuzuGraphStore) -> None:
    assert score_pair(store, "u", "v").resource_allocation == pytest.approx(0.5)


def test_preferential_is_product_of_degrees(store: KuzuGraphStore) -> None:
    # deg(u)=2, deg(v)=2
    assert score_pair(store, "u", "v").preferential == 4


def test_rank_candidates_orders_strong_above_weak(store: KuzuGraphStore) -> None:
    ranked = rank_candidates(store, "S", ["WC", "SC"])
    assert [r.target for r in ranked] == ["SC", "WC"]
    assert ranked[0].adamic_adar > ranked[1].adamic_adar


def test_score_pair_symmetric(store: KuzuGraphStore) -> None:
    ab = score_pair(store, "A", "B")
    ba = score_pair(store, "B", "A")
    assert ab.common == ba.common
    assert ab.jaccard == pytest.approx(ba.jaccard)
    assert ab.adamic_adar == pytest.approx(ba.adamic_adar)


def test_as_dict_exposes_all_metrics(store: KuzuGraphStore) -> None:
    d = score_pair(store, "u", "v").as_dict()
    assert set(d) == {
        "source",
        "target",
        "common",
        "jaccard",
        "adamic_adar",
        "resource_allocation",
        "preferential",
    }
    assert isinstance(LinkScore(*("u", "v", 1, 0.5, 0.1, 0.2, 4)).as_dict(), dict)
