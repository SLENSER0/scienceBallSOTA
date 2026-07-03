"""Тесты перечисления простых путей ``POST /graph/path`` (§14.6).

Ручные, проверяемые сценарии для :func:`enumerate_paths`: прямое ребро, два
непересекающихся маршрута, отсутствие маршрута, циклы, ограничение длины,
фильтр по типу ребра и усечение по ``max_paths``.

Hand-checkable scenarios for :func:`enumerate_paths`.
"""

from __future__ import annotations

from api_gateway.path_enumerate import PathResult, enumerate_paths


def _edge(source: str, target: str, type_: str = "RELATED") -> dict[str, str]:
    """Собрать ребро с типом / build a typed edge (§14.6)."""
    return {"source": source, "target": target, "type": type_}


def test_single_direct_edge_yields_one_path() -> None:
    """(1) Прямое ребро A→B даёт единственный путь (A, B)."""
    result = enumerate_paths([_edge("A", "B")], "A", "B")
    assert result.paths == (("A", "B"),)
    assert result.count == 1
    assert result.truncated is False


def test_two_disjoint_routes_yield_two_paths() -> None:
    """(2) Маршруты A→B→D и A→C→D дают два пути."""
    edges = [
        _edge("A", "B"),
        _edge("B", "D"),
        _edge("A", "C"),
        _edge("C", "D"),
    ]
    result = enumerate_paths(edges, "A", "D")
    assert result.count == 2
    assert set(result.paths) == {("A", "B", "D"), ("A", "C", "D")}
    assert result.truncated is False


def test_no_route_yields_empty() -> None:
    """(3) Нет маршрута → пути пусты, count == 0."""
    result = enumerate_paths([_edge("A", "B")], "A", "Z")
    assert result.paths == ()
    assert result.count == 0
    assert result.truncated is False


def test_cycle_does_not_revisit_node() -> None:
    """(4) Цикл не порождает путь с повтором узла (только простые)."""
    edges = [
        _edge("A", "B"),
        _edge("B", "C"),
        _edge("C", "A"),  # замыкает цикл / closes the cycle
        _edge("C", "D"),
    ]
    result = enumerate_paths(edges, "A", "D")
    assert result.paths == (("A", "B", "C", "D"),)
    for path in result.paths:
        assert len(path) == len(set(path))  # без повторов узлов / simple path


def test_route_longer_than_max_length_excluded() -> None:
    """(5) Маршрут длиннее ``max_length`` исключается."""
    edges = [
        _edge("A", "B"),
        _edge("B", "C"),
        _edge("C", "D"),
        _edge("D", "E"),  # A→…→E имеет 4 ребра / four hops
    ]
    result = enumerate_paths(edges, "A", "E", max_length=3)
    assert result.count == 0
    assert result.paths == ()
    # С запасом длины путь появляется / with a larger cap the path appears.
    ok = enumerate_paths(edges, "A", "E", max_length=4)
    assert ok.paths == (("A", "B", "C", "D", "E"),)


def test_edge_types_filter_excludes_other_types() -> None:
    """(6) ``edge_types={'RELATED'}`` исключает путь через ребро CONTRADICTS."""
    edges = [
        _edge("A", "B", "RELATED"),
        _edge("B", "D", "RELATED"),
        _edge("A", "C", "RELATED"),
        _edge("C", "D", "CONTRADICTS"),  # маршрут через C отфильтрован
    ]
    result = enumerate_paths(edges, "A", "D", edge_types={"RELATED"})
    assert result.paths == (("A", "B", "D"),)
    assert result.count == 1
    # Без фильтра доступны оба маршрута / both routes without the filter.
    both = enumerate_paths(edges, "A", "D")
    assert both.count == 2


def test_max_paths_cap_sets_truncated() -> None:
    """(7) ``max_paths=1`` на графе с двумя путями: count == 1, truncated True."""
    edges = [
        _edge("A", "B"),
        _edge("B", "D"),
        _edge("A", "C"),
        _edge("C", "D"),
    ]
    result = enumerate_paths(edges, "A", "D", max_paths=1)
    assert result.count == 1
    assert result.truncated is True


def test_as_dict_keys() -> None:
    """(8) Ключи ``as_dict`` — paths/count/truncated."""
    result = enumerate_paths([_edge("A", "B")], "A", "B")
    assert isinstance(result, PathResult)
    wire = result.as_dict()
    assert set(wire) == {"paths", "count", "truncated"}
    assert wire["paths"] == [["A", "B"]]
    assert wire["count"] == 1
    assert wire["truncated"] is False
