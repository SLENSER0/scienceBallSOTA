"""Hand-checkable tests for §12.4 positional Borda-count fusion."""

from __future__ import annotations

from kg_retrievers.borda_fusion import (
    BordaResult,
    borda_fuse,
    borda_points,
    weighted_borda,
)


def test_borda_points_top_of_length_three() -> None:
    """Assertion (1): borda_points(0, 3) == 3 — топ списка длины 3."""
    assert borda_points(0, 3) == 3


def test_borda_points_last_of_length_three() -> None:
    """Assertion (2): borda_points(2, 3) == 1 — последний элемент длины 3."""
    assert borda_points(2, 3) == 1


def _sample() -> dict[str, list[str]]:
    return {"A": ["x", "y", "z"], "B": ["y", "x", "z"]}


def test_points_summed_across_lists() -> None:
    """Assertion (3): x=3+2=5, y=2+3=5, z=1+1=2."""
    by_id = {r.doc_id: r.points for r in borda_fuse(_sample())}
    assert by_id == {"x": 5.0, "y": 5.0, "z": 2.0}


def test_tie_broken_by_lower_doc_id() -> None:
    """Assertion (4): ничья x/y разрешается — 'x' раньше 'y'."""
    order = [r.doc_id for r in borda_fuse(_sample())]
    assert order.index("x") < order.index("y")


def test_z_ranks_last() -> None:
    """Assertion (5): z с наименьшими очками — в конце."""
    order = [r.doc_id for r in borda_fuse(_sample())]
    assert order[-1] == "z"


def test_appearances_counts_lists() -> None:
    """Assertion (6): x встречается в обоих списках -> appearances == 2."""
    by_id = {r.doc_id: r.appearances for r in borda_fuse(_sample())}
    assert by_id["x"] == 2


def test_weighted_borda_zeroes_out_second_list() -> None:
    """Assertion (7): weights {A:1.0, B:0.0} -> x=3.0, y=2.0, z=1.0."""
    results = weighted_borda(_sample(), {"A": 1.0, "B": 0.0})
    by_id = {r.doc_id: r.points for r in results}
    assert by_id == {"x": 3.0, "y": 2.0, "z": 1.0}


def test_missing_doc_contributes_zero_from_that_list() -> None:
    """Assertion (8): документ, отсутствующий в списке, добавляет 0 очков оттуда."""
    rankings = {"A": ["x", "y"], "B": ["x"]}
    #   x: A -> len2-rank0 = 2, B -> len1-rank0 = 1 => 3
    #   y: A -> len2-rank1 = 1, B -> отсутствует => +0 => 1
    by_id = {r.doc_id: r.points for r in borda_fuse(rankings)}
    assert by_id == {"x": 3.0, "y": 1.0}
    appearances = {r.doc_id: r.appearances for r in borda_fuse(rankings)}
    assert appearances == {"x": 2, "y": 1}


def test_as_dict_exposes_points_and_appearances() -> None:
    """Assertion (9): as_dict() отдаёт points и appearances."""
    result = BordaResult(doc_id="x", points=5.0, appearances=2)
    assert result.as_dict() == {"doc_id": "x", "points": 5.0, "appearances": 2}


def test_borda_result_is_frozen() -> None:
    """Frozen dataclass — атрибуты неизменяемы (house style)."""
    result = BordaResult(doc_id="x", points=1.0, appearances=1)
    try:
        result.points = 2.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("BordaResult must be frozen")
