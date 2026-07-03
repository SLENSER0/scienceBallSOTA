"""Tests for §11.10 blue/green Qdrant collection alias planner.

RU: Проверяет имена коллекций, план swap, retention и инвариант разбиения.
EN: Checks collection names, swap plan, retention and the partition invariant.
"""

from __future__ import annotations

import pytest

from kg_retrievers.graphrag_collection_alias import (
    AliasPlan,
    collection_name,
    plan_swap,
)


def test_collection_name_default_base() -> None:
    assert collection_name("b1") == "graphrag_community_summaries_b1"


def test_collection_name_custom_base() -> None:
    assert collection_name("v9", base="foo") == "foo_v9"


def test_plan_swap_active_collection() -> None:
    plan = plan_swap("b3", ["b1", "b2", "b3"], retain_k=1)
    assert plan.active_collection == "graphrag_community_summaries_b3"


def test_plan_swap_to_drop_and_keep() -> None:
    plan = plan_swap("b3", ["b1", "b2", "b3"], retain_k=1)
    assert plan.to_drop == ("graphrag_community_summaries_b1",)
    assert "graphrag_community_summaries_b3" in plan.to_keep
    # RU: новейшая неактивная (b2) тоже удерживается при retain_k=1.
    # EN: the newest non-active (b2) is also retained at retain_k=1.
    assert "graphrag_community_summaries_b2" in plan.to_keep


def test_active_never_dropped_even_retain_zero() -> None:
    plan = plan_swap("b3", ["b1", "b2", "b3"], retain_k=0)
    assert plan.active_collection not in plan.to_drop
    assert "graphrag_community_summaries_b3" in plan.to_keep
    assert plan.to_drop == (
        "graphrag_community_summaries_b1",
        "graphrag_community_summaries_b2",
    )


def test_plan_swap_retain_k_larger_than_history() -> None:
    plan = plan_swap("b1", ["b1"], 2)
    assert plan.to_drop == ()
    assert plan.to_keep == ("graphrag_community_summaries_b1",)


def test_as_dict_alias_is_base() -> None:
    plan = plan_swap("b3", ["b1", "b2", "b3"], retain_k=1)
    assert plan.as_dict()["alias"] == "graphrag_community_summaries"


def test_partition_invariant() -> None:
    versions = ["b1", "b2", "b3", "b4", "b5"]
    for active in versions:
        for retain_k in range(0, 6):
            plan = plan_swap(active, versions, retain_k=retain_k)
            assert len(plan.to_keep) + len(plan.to_drop) == len(versions)
            # RU: активная коллекция всегда сохраняется, никогда не удаляется.
            # EN: the active collection is always kept, never dropped.
            active_col = collection_name(active)
            assert active_col in plan.to_keep
            assert active_col not in plan.to_drop


def test_retention_counts() -> None:
    # RU: retain_k=2 удерживает активную + 2 новейшие неактивные (b3,b4).
    # EN: retain_k=2 keeps active + the 2 newest non-active (b3,b4).
    plan = plan_swap("b5", ["b1", "b2", "b3", "b4", "b5"], retain_k=2)
    assert plan.to_drop == (
        "graphrag_community_summaries_b1",
        "graphrag_community_summaries_b2",
    )
    assert set(plan.to_keep) == {
        "graphrag_community_summaries_b3",
        "graphrag_community_summaries_b4",
        "graphrag_community_summaries_b5",
    }


def test_active_is_oldest() -> None:
    # RU: активная — самая старая; новейшие retain_k берутся из неактивных.
    # EN: active is oldest; newest retain_k drawn from non-active versions.
    plan = plan_swap("b1", ["b1", "b2", "b3"], retain_k=1)
    assert plan.active_collection == "graphrag_community_summaries_b1"
    assert set(plan.to_keep) == {
        "graphrag_community_summaries_b1",
        "graphrag_community_summaries_b3",
    }
    assert plan.to_drop == ("graphrag_community_summaries_b2",)


def test_negative_retain_k_raises() -> None:
    with pytest.raises(ValueError):
        plan_swap("b1", ["b1"], retain_k=-1)


def test_alias_plan_frozen() -> None:
    plan = AliasPlan("a", "a_b1", ("a_b1",), ())
    with pytest.raises(AttributeError):
        plan.alias = "z"  # type: ignore[misc]
