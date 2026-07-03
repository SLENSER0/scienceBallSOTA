"""Hand-checked tests for lost-in-the-middle packing reorder (§12.9).

Каждое ожидаемое значение посчитано вручную по правилу «складывания» (§12.9): rank0→0,
rank1→last, rank2→1, rank3→second-last, …
"""

from __future__ import annotations

from kg_retrievers.lost_in_middle_reorder import (
    ReorderResult,
    fold_order,
    reorder_hits,
)

# ---------------------------------------------------------------------------
# fold_order — interleave outward-in
# ---------------------------------------------------------------------------


def test_fold_order_five() -> None:
    """rank0→0, rank1→4, rank2→1, rank3→3, rank4→2 → ['a','c','e','d','b']."""
    assert fold_order(["a", "b", "c", "d", "e"]) == ["a", "c", "e", "d", "b"]


def test_fold_order_two() -> None:
    """rank0→0, rank1→last(=1); two elements are unchanged."""
    assert fold_order(["a", "b"]) == ["a", "b"]


def test_fold_order_one() -> None:
    """A single element folds to itself."""
    assert fold_order(["a"]) == ["a"]


def test_fold_order_empty() -> None:
    """Empty input yields an empty list."""
    assert fold_order([]) == []


def test_fold_order_four() -> None:
    """rank0→0, rank1→3, rank2→1, rank3→2 → ['a','c','d','b'] (extra hand check)."""
    assert fold_order(["a", "b", "c", "d"]) == ["a", "c", "d", "b"]


# ---------------------------------------------------------------------------
# reorder_hits — sort-by-score then fold
# ---------------------------------------------------------------------------

# Deliberately unsorted by score. Sorted desc: e(0.95) d(0.90) c(0.80) b(0.70) a(0.50).
# Folded ids: e→pos0, d→pos4, c→pos1, b→pos3, a→pos2 → ['e','c','a','b','d'].
_UNSORTED = [
    {"id": "a", "score": 0.50},
    {"id": "b", "score": 0.70},
    {"id": "c", "score": 0.80},
    {"id": "d", "score": 0.90},
    {"id": "e", "score": 0.95},
]


def test_reorder_sorts_before_folding_best_at_head() -> None:
    """Best-scored id (e) lands at position 0 after the score sort + fold."""
    res = reorder_hits(_UNSORTED)
    assert res.order[0] == "e"
    assert res.order == ("e", "c", "a", "b", "d")


def test_reorder_second_best_at_tail() -> None:
    """Second-best id (d) lands at the last position."""
    res = reorder_hits(_UNSORTED)
    assert res.order[-1] == "d"


def test_reorder_head_tail_split() -> None:
    """head_ids = first ceil(5/2)=3 folded ids; tail_ids = the remaining 2."""
    res = reorder_hits(_UNSORTED)
    assert res.head_ids == ("e", "c", "a")
    assert res.tail_ids == ("b", "d")


def test_reorder_order_length_matches_input() -> None:
    """as_dict()['order'] length equals the number of hits."""
    res = reorder_hits(_UNSORTED)
    assert len(res.as_dict()["order"]) == len(_UNSORTED)


def test_reorder_result_is_frozen() -> None:
    """ReorderResult is an immutable (frozen) dataclass."""
    res = reorder_hits(_UNSORTED)
    assert isinstance(res, ReorderResult)
    try:
        res.order = ()  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("ReorderResult must be frozen")


def test_reorder_as_dict_shape() -> None:
    """as_dict() exposes list copies of order/head_ids/tail_ids."""
    res = reorder_hits(_UNSORTED)
    d = res.as_dict()
    assert d == {
        "order": ["e", "c", "a", "b", "d"],
        "head_ids": ["e", "c", "a"],
        "tail_ids": ["b", "d"],
    }


def test_reorder_empty() -> None:
    """Empty hits → all-empty ReorderResult."""
    res = reorder_hits([])
    assert res.as_dict() == {"order": [], "head_ids": [], "tail_ids": []}


def test_reorder_custom_keys() -> None:
    """Custom score_key/id_key are honored; best 'q' by weight heads the order."""
    hits = [
        {"node": "p", "weight": 0.1},
        {"node": "q", "weight": 0.9},
        {"node": "r", "weight": 0.5},
    ]
    res = reorder_hits(hits, score_key="weight", id_key="node")
    # Sorted desc: q(0.9) r(0.5) p(0.1). Fold: q→0, r→2, p→1 → ['q','p','r'].
    assert res.order == ("q", "p", "r")
    assert res.head_ids == ("q", "p")
    assert res.tail_ids == ("r",)


def test_reorder_stable_on_ties() -> None:
    """Equal scores keep input order before folding (stable sort)."""
    hits = [
        {"id": "x", "score": 1.0},
        {"id": "y", "score": 1.0},
        {"id": "z", "score": 1.0},
    ]
    res = reorder_hits(hits)
    # Stable desc order: x, y, z. Fold: x→0, y→2, z→1 → ['x','z','y'].
    assert res.order == ("x", "z", "y")
