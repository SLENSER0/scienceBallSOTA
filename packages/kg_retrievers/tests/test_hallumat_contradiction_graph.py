"""§15.4 / §15 — tests for HalluMat contradiction-graph grouping + PHCS."""

from __future__ import annotations

from kg_retrievers import hallumat_contradiction_graph as hg
from kg_retrievers.hallumat_contradiction_graph import (
    ContradictionGraph,
    build_contradiction_graph,
    phcs,
)


def test_two_mutually_contradicting_claims_form_one_cluster() -> None:
    """Пара (c1, c2): оба утверждения попадают в один кластер."""
    graph = build_contradiction_graph([("c1", "c2")])
    assert graph.nodes == ("c1", "c2")
    assert graph.edges == (("c1", "c2"),)
    assert graph.clusters == (("c1", "c2"),)


def test_disjoint_contradictions_separate_clusters() -> None:
    """Непересекающиеся противоречия дают отдельные кластеры."""
    graph = build_contradiction_graph([("c1", "c2"), ("c3", "c4")])
    assert graph.clusters == (("c1", "c2"), ("c3", "c4"))
    assert len(graph.clusters) == 2


def test_transitive_cluster_merge() -> None:
    """a↔b и b↔c транзитивно сливаются в один кластер {a, b, c}."""
    graph = build_contradiction_graph([("c1", "c2"), ("c2", "c3")])
    assert graph.clusters == (("c1", "c2", "c3"),)
    assert graph.nodes == ("c1", "c2", "c3")
    assert set(graph.edges) == {("c1", "c2"), ("c2", "c3")}


def test_phcs_fraction() -> None:
    """PHCS = contradicted / total: 2 из 4 утверждений противоречат -> 0.5."""
    assert phcs([("c1", "c2")], n_claims=4) == 0.5


def test_phcs_zero_when_no_contradictions() -> None:
    """Нет противоречий -> PHCS 0.0 даже при непустом наборе утверждений."""
    assert phcs([], n_claims=5) == 0.0


def test_phcs_zero_when_no_claims() -> None:
    """n_claims <= 0 -> PHCS 0.0 (защита от деления на ноль)."""
    assert phcs([("c1", "c2")], n_claims=0) == 0.0


def test_phcs_counts_distinct_claims_across_pairs() -> None:
    """Транзитивная цепочка из 3 утверждений при total=6 -> 3/6 = 0.5."""
    assert phcs([("c1", "c2"), ("c2", "c3")], n_claims=6) == 0.5


def test_as_dict_shape() -> None:
    """as_dict() возвращает списки nodes/edges/clusters (JSON-friendly)."""
    graph = build_contradiction_graph([("c1", "c2"), ("c3", "c4")])
    payload = graph.as_dict()
    assert payload == {
        "nodes": ["c1", "c2", "c3", "c4"],
        "edges": [["c1", "c2"], ["c3", "c4"]],
        "clusters": [["c1", "c2"], ["c3", "c4"]],
    }


def test_empty_input_is_empty_graph() -> None:
    """Пустой вход -> пустой граф и PHCS 0.0."""
    graph = build_contradiction_graph([])
    assert graph.nodes == ()
    assert graph.edges == ()
    assert graph.clusters == ()
    assert phcs([], n_claims=0) == 0.0


def test_duplicate_and_reversed_pairs_deduplicated() -> None:
    """Дубли и перевёрнутые пары нормализуются в одно ребро."""
    graph = build_contradiction_graph([("c2", "c1"), ("c1", "c2")])
    assert graph.edges == (("c1", "c2"),)
    assert graph.clusters == (("c1", "c2"),)


def test_graph_is_frozen() -> None:
    """ContradictionGraph — frozen dataclass (нельзя мутировать)."""
    graph = build_contradiction_graph([("c1", "c2")])
    assert isinstance(graph, ContradictionGraph)
    try:
        graph.nodes = ("x",)  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ContradictionGraph should be immutable")


def test_module_docstring_cites_arxiv_paper() -> None:
    """Жёсткое требование: docstring модуля цитирует arXiv:2512.22396."""
    assert hg.__doc__ is not None
    assert "2512.22396" in hg.__doc__
