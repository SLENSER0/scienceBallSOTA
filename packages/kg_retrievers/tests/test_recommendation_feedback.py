"""Tests for §24.12 feedback-adjusted recommendation re-ranking.

RU: Проверяет, что обратная связь корректирует ranking рекомендаций.
EN: Verifies that feedback adjusts recommendation ranking (§24.12).
"""

from __future__ import annotations

from kg_retrievers.recommendation_feedback import (
    AdjustedRecommendation,
    apply_feedback,
)


def test_upvotes_gain_up_weight() -> None:
    """up=2 down=0 adds exactly 2 * up_weight to the score (§24.12)."""
    items = [{"item_id": "a", "base_score": 1.0}]
    feedback = {"a": {"up": 2, "down": 0}}
    result = apply_feedback(items, feedback, up_weight=0.1, down_weight=0.1)
    assert len(result) == 1
    assert result[0].feedback_delta == 2 * 0.1
    assert result[0].adjusted_score == 1.0 + 2 * 0.1


def test_downvotes_lose_down_weight() -> None:
    """up=0 down=3 subtracts exactly 3 * down_weight (§24.12)."""
    items = [{"item_id": "a", "base_score": 1.0}]
    feedback = {"a": {"up": 0, "down": 3}}
    result = apply_feedback(items, feedback, up_weight=0.1, down_weight=0.1)
    assert result[0].feedback_delta == -3 * 0.1
    assert result[0].adjusted_score == 1.0 - 3 * 0.1


def test_item_absent_from_feedback_unchanged() -> None:
    """An item with no feedback entry gets delta 0.0 and keeps base score (§24.12)."""
    items = [{"item_id": "a", "base_score": 0.7}]
    result = apply_feedback(items, {})
    assert result[0].feedback_delta == 0.0
    assert result[0].adjusted_score == 0.7


def test_downvotes_flip_order_and_ranks() -> None:
    """Enough downvotes flip two items' order and their ranks (§24.12)."""
    items = [
        {"item_id": "a", "base_score": 1.0},
        {"item_id": "b", "base_score": 0.9},
    ]
    # a starts ahead (1.0 > 0.9); heavy downvotes on a drop it below b.
    feedback = {"a": {"up": 0, "down": 5}}  # a -> 1.0 - 0.5 = 0.5
    result = apply_feedback(items, feedback, up_weight=0.1, down_weight=0.1)
    by_id = {r.item_id: r for r in result}
    assert by_id["a"].adjusted_score == 0.5
    assert by_id["b"].adjusted_score == 0.9
    # b now ranks 1, a ranks 2.
    assert by_id["b"].rank == 1
    assert by_id["a"].rank == 2
    assert result[0].item_id == "b"
    assert result[1].item_id == "a"


def test_feedback_delta_exact_hand_case() -> None:
    """feedback_delta computed exactly for a hand-checked case (§24.12)."""
    items = [{"item_id": "x", "base_score": 2.0}]
    # up=4, down=1, up_weight=0.25, down_weight=0.5 -> 4*0.25 - 1*0.5 = 1.0 - 0.5 = 0.5
    feedback = {"x": {"up": 4, "down": 1}}
    result = apply_feedback(items, feedback, up_weight=0.25, down_weight=0.5)
    assert result[0].feedback_delta == 0.5
    assert result[0].adjusted_score == 2.5


def test_tie_adjusted_score_orders_by_item_id() -> None:
    """Equal adjusted_score ties break by item_id ascending (§24.12)."""
    items = [
        {"item_id": "b", "base_score": 0.5},
        {"item_id": "a", "base_score": 0.5},
        {"item_id": "c", "base_score": 0.5},
    ]
    result = apply_feedback(items, {})
    assert [r.item_id for r in result] == ["a", "b", "c"]
    assert [r.rank for r in result] == [1, 2, 3]


def test_empty_items_returns_empty() -> None:
    """Empty items list yields an empty result (§24.12)."""
    assert apply_feedback([], {}) == []


def test_as_dict_adjusted_score_is_base_plus_delta() -> None:
    """as_dict()['adjusted_score'] == base + delta (§24.12, house style)."""
    items = [{"item_id": "a", "base_score": 1.5}]
    feedback = {"a": {"up": 3, "down": 1}}  # 3*0.1 - 1*0.1 = 0.2
    result = apply_feedback(items, feedback)
    d = result[0].as_dict()
    assert isinstance(result[0], AdjustedRecommendation)
    assert d["adjusted_score"] == d["base_score"] + d["feedback_delta"]
    assert d["base_score"] == 1.5
    assert d["feedback_delta"] == 3 * 0.1 - 1 * 0.1
    assert d["rank"] == 1
