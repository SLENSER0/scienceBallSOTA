"""Hand-checkable tests for §12.4 round-robin & team-draft interleaving."""

from __future__ import annotations

from kg_retrievers.list_interleave import (
    InterleaveResult,
    round_robin,
    team_draft,
)


def test_round_robin_alternates_two_sources() -> None:
    """Assertion (1): {s1:[a,c], s2:[b,d]} -> order (a,b,c,d)."""
    result = round_robin({"s1": ["a", "c"], "s2": ["b", "d"]})
    assert result.order == ("a", "b", "c", "d")


def test_round_robin_dedupes_first_occurrence_wins() -> None:
    """Assertion (2): {s1:[a,b], s2:[a,c]} -> (a,b,c), source_of[a]=='s1'."""
    result = round_robin({"s1": ["a", "b"], "s2": ["a", "c"]})
    assert result.order == ("a", "b", "c")
    assert result.source_of["a"] == "s1"


def test_round_robin_single_source_preserves_order() -> None:
    """Assertion (3): один источник -> его порядок как есть."""
    result = round_robin({"only": ["z", "y", "x"]})
    assert result.order == ("z", "y", "x")
    assert result.source_of == {"z": "only", "y": "only", "x": "only"}


def test_round_robin_empty_rankings_empty_order() -> None:
    """Assertion (4): пустой rankings -> пустой order."""
    result = round_robin({})
    assert result.order == ()
    assert result.source_of == {}


def test_team_draft_alternates_starting_with_list_a() -> None:
    """Assertion (5): team_draft([a,c],[b,d]) -> (a,b,c,d)."""
    result = team_draft(["a", "c"], ["b", "d"])
    assert result.order == ("a", "b", "c", "d")
    assert result.source_of == {"a": "list_a", "b": "list_b", "c": "list_a", "d": "list_b"}


def test_team_draft_preserves_within_list_relative_order() -> None:
    """Assertion (6): относительный порядок внутри каждого списка сохранён."""
    result = team_draft(["a", "b", "c"], ["p", "q", "r"])
    order = result.order
    # list_a: a before b before c; list_b: p before q before r
    assert order.index("a") < order.index("b") < order.index("c")
    assert order.index("p") < order.index("q") < order.index("r")


def test_team_draft_skips_duplicate_already_drafted() -> None:
    """Assertion (7): id, уже выбранный из другого списка, пропускается."""
    # list_a=[a,b], list_b=[a,c]:
    #   turn a -> a (list_a); turn b -> a seen, take c (list_b);
    #   turn a -> b (list_a); b exhausted -> stop.
    result = team_draft(["a", "b"], ["a", "c"])
    assert result.order == ("a", "c", "b")
    assert result.source_of == {"a": "list_a", "c": "list_b", "b": "list_a"}


def test_team_draft_uneven_lists_drains_remainder() -> None:
    """Longer list продолжает отдавать id, когда другой исчерпан."""
    result = team_draft(["a", "b", "c"], ["x"])
    #   a (A); x (B); b (A); B empty -> c (A)
    assert result.order == ("a", "x", "b", "c")


def test_as_dict_exposes_order_and_source_of() -> None:
    """Assertion (8): as_dict() отдаёт order и source_of."""
    result = InterleaveResult(order=("a", "b"), source_of={"a": "s1", "b": "s2"})
    assert result.as_dict() == {
        "order": ("a", "b"),
        "source_of": {"a": "s1", "b": "s2"},
    }


def test_interleave_result_is_frozen() -> None:
    """Frozen dataclass — атрибуты неизменяемы (house style)."""
    result = InterleaveResult(order=("a",), source_of={"a": "s1"})
    try:
        result.order = ("b",)  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("InterleaveResult must be frozen")
