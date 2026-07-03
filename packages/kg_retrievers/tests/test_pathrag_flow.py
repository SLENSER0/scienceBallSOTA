"""PathRAG flow-pruned path retrieval over a temp KuzuGraphStore (§12.2 / §12.5).

Все ожидаемые значения надёжности посчитаны вручную по формуле
``reliability = decay ** hops * ∏ edge_weight`` с параметрами по умолчанию
``decay = 0.8`` и ``weight_default = 0.8`` (вес ребра = ``r.confidence``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import kg_retrievers.pathrag_flow as pathrag_flow
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.pathrag_flow import find_paths, linearize


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _edge(s: KuzuGraphStore, src: str, dst: str, rel: str, conf: float | None = None) -> None:
    s.upsert_node(src, "Entity", name=src)
    s.upsert_node(dst, "Entity", name=dst)
    if conf is None:
        s.upsert_edge(src, dst, rel)
    else:
        s.upsert_edge(src, dst, rel, confidence=conf)


def test_docstring_cites_arxiv() -> None:
    # Hard requirement: the module must cite the source paper (arXiv:2502.14902).
    assert pathrag_flow.__doc__ is not None
    assert "2502.14902" in pathrag_flow.__doc__


def test_short_high_conf_outranks_long_low_conf(store: KuzuGraphStore) -> None:
    _edge(store, "s", "t", "DIRECT", conf=0.9)  # 1 hop:  0.8 * 0.9        = 0.72
    _edge(store, "s", "a", "R", conf=0.5)  # 3 hops: 0.8^3 * 0.5^3 = 0.064
    _edge(store, "a", "b", "R", conf=0.5)
    _edge(store, "b", "t", "R", conf=0.5)

    res = find_paths(store, "s", "t")

    assert res.paths[0]["nodes"] == ["s", "t"]
    assert res.paths[0]["reliability"] == pytest.approx(0.72)
    assert res.paths[1]["nodes"] == ["s", "a", "b", "t"]
    assert res.paths[1]["reliability"] == pytest.approx(0.064)
    assert res.paths[0]["reliability"] > res.paths[1]["reliability"]


def test_reliability_decays_with_hops(store: KuzuGraphStore) -> None:
    # Equal edge weights (1.0): only path length differs, so decay must dominate.
    _edge(store, "x", "y", "R", conf=1.0)  # 1 hop:  0.8
    _edge(store, "x", "p", "R", conf=1.0)  # 2 hops: 0.64
    _edge(store, "p", "y", "R", conf=1.0)

    res = find_paths(store, "x", "y")
    by_len = {len(p["edges"]): p["reliability"] for p in res.paths}

    assert by_len[1] == pytest.approx(0.8)
    assert by_len[2] == pytest.approx(0.64)
    assert by_len[1] > by_len[2]


def test_reliability_exact_value(store: KuzuGraphStore) -> None:
    _edge(store, "a", "b", "R", conf=0.5)  # 0.8^2 * 0.5 * 0.6 = 0.192
    _edge(store, "b", "c", "R", conf=0.6)

    res = find_paths(store, "a", "c")

    assert len(res.paths) == 1
    assert res.paths[0]["reliability"] == pytest.approx(0.192)


def test_default_weight_when_confidence_missing(store: KuzuGraphStore) -> None:
    _edge(store, "a", "b", "R")  # no confidence -> weight_default 0.8

    res = find_paths(store, "a", "b")
    path = res.paths[0]

    assert path["edges"][0]["weight"] == pytest.approx(0.8)
    assert path["reliability"] == pytest.approx(0.64)  # 0.8 (decay) * 0.8 (weight)


def test_top_n_prunes(store: KuzuGraphStore) -> None:
    _edge(store, "s", "t", "DIRECT", conf=0.9)  # 0.72       -> kept
    for name, conf in [("m1", 0.7), ("m2", 0.6), ("m3", 0.5), ("m4", 0.4)]:
        _edge(store, "s", name, "R", conf=conf)  # two-hop paths, distinct scores
        _edge(store, name, "t", "R", conf=conf)

    res = find_paths(store, "s", "t", top_n=2)

    assert len(res.paths) == 2
    assert len(res.pruned) == 3
    assert res.paths[0]["nodes"] == ["s", "t"]  # highest reliability
    assert res.paths[1]["nodes"] == ["s", "m1", "t"]  # next: 0.64 * 0.49 = 0.3136
    kept_min = min(p["reliability"] for p in res.paths)
    pruned_max = max(p["reliability"] for p in res.pruned)
    assert kept_min > pruned_max  # flow-based pruning keeps the strongest paths


def test_no_path_returns_empty(store: KuzuGraphStore) -> None:
    _edge(store, "w", "u", "R", conf=0.9)  # only w->u; no directed u->w path exists

    res = find_paths(store, "u", "w")

    assert res.paths == ()
    assert res.pruned == ()


def test_linearize_renders_arrow(store: KuzuGraphStore) -> None:
    _edge(store, "a", "b", "REL", conf=0.9)

    res = find_paths(store, "a", "b")

    assert linearize(res.paths[0]) == "a -[REL]-> b"
    assert linearize({"edges": []}) == ""


def test_linearize_chains_multi_hop(store: KuzuGraphStore) -> None:
    _edge(store, "a", "b", "R1", conf=0.9)
    _edge(store, "b", "c", "R2", conf=0.9)

    res = find_paths(store, "a", "c")

    assert linearize(res.paths[0]) == "a -[R1]-> b -[R2]-> c"


def test_as_dict_shape_and_copy(store: KuzuGraphStore) -> None:
    _edge(store, "a", "b", "R", conf=0.9)

    res = find_paths(store, "a", "b")
    d = res.as_dict()

    assert set(d) == {"paths", "pruned"}
    assert isinstance(d["paths"], list)
    assert set(d["paths"][0]) == {"nodes", "edges", "reliability"}
    assert d["paths"][0]["nodes"] == ["a", "b"]

    d["paths"][0]["nodes"].append("mutated")  # as_dict must deep-copy
    assert res.paths[0]["nodes"] == ["a", "b"]
