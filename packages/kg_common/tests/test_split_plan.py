"""Tests for the §16.6 split redistribution planner (RU/EN)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.storage.split_plan import SplitPlan, plan_split


def _edge(eid: str) -> dict:
    return {"id": eid, "type": "REL"}


def _ev(vid: str) -> dict:
    return {"id": vid, "quote": "..."}


def test_single_new_id_raises() -> None:
    """(1) len(new_ids)==1 is not a valid split."""
    with pytest.raises(ValueError):
        plan_split("s", ["n1"], [], [], {"n1": []})


def test_edge_assigned_to_named_bucket() -> None:
    """(2) edge 'e1' listed under 'n1' -> assigned to 'n1'."""
    plan = plan_split(
        "s",
        ["n1", "n2"],
        [_edge("e1")],
        [],
        {"n1": ["e1"], "n2": []},
    )
    assert plan.edge_assignments["e1"] == "n1"


def test_unlisted_evidence_is_unassigned() -> None:
    """(3) evidence 'ev9' in no bucket -> lands in unassigned."""
    plan = plan_split(
        "s",
        ["n1", "n2"],
        [],
        [_ev("ev9")],
        {"n1": [], "n2": []},
    )
    assert "ev9" in plan.unassigned
    assert plan.evidence_assignments == {}


def test_double_claim_raises() -> None:
    """(4) same id in n1 and n2 buckets is a conflict."""
    with pytest.raises(ValueError):
        plan_split(
            "s",
            ["n1", "n2"],
            [_edge("e1")],
            [],
            {"n1": ["e1"], "n2": ["e1"]},
        )


def test_as_dict_shape() -> None:
    """(5) as_dict() carries source_id and a list-typed 'unassigned'."""
    plan = plan_split(
        "s",
        ["n1", "n2"],
        [_edge("e1")],
        [_ev("ev9")],
        {"n1": ["e1"], "n2": []},
    )
    d = plan.as_dict()
    assert d["source_id"] == "s"
    assert isinstance(d["unassigned"], list)
    assert d["unassigned"] == ["ev9"]
    assert d["edge_assignments"] == {"e1": "n1"}


def test_all_assigned_gives_empty_unassigned() -> None:
    """(6) when every element is claimed, unassigned is empty tuple."""
    plan = plan_split(
        "s",
        ["n1", "n2"],
        [_edge("e1"), _edge("e2")],
        [_ev("ev1")],
        {"n1": ["e1", "ev1"], "n2": ["e2"]},
    )
    assert plan.unassigned == ()
    assert plan.edge_assignments == {"e1": "n1", "e2": "n2"}
    assert plan.evidence_assignments == {"ev1": "n1"}


def test_new_ids_order_preserved() -> None:
    """(7) plan.new_ids preserves the input order."""
    plan = plan_split(
        "s",
        ["nb", "na", "nc"],
        [],
        [],
        {},
    )
    assert plan.new_ids == ("nb", "na", "nc")


def test_frozen_dataclass() -> None:
    """SplitPlan is immutable (frozen)."""
    plan = plan_split("s", ["n1", "n2"], [], [], {})
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.source_id = "x"  # type: ignore[misc]


def test_returns_split_plan_instance() -> None:
    plan = plan_split("s", ["n1", "n2"], [], [], {})
    assert isinstance(plan, SplitPlan)
