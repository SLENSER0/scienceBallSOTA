"""Tests for the contradiction-resolution planner (§16.6).

RU/EN: противоречие / contradiction, победитель / winner, гашение / quench.
"""

from __future__ import annotations

import pytest

from kg_common.storage.contradiction_resolution import ResolutionPlan, plan_resolution


def _contradiction(claim_ids: list[str], edges: list[str]) -> dict:
    """Собрать минимальный dict противоречия для планировщика."""
    return {"id": "contra-1", "claim_ids": claim_ids, "contradicts_edges": edges}


def test_winner_not_in_claims_raises_keyerror() -> None:
    """(1) Победитель не в claim_ids → KeyError."""
    contra = _contradiction(["c1", "c2"], ["e1"])
    with pytest.raises(KeyError):
        plan_resolution(contra, winner_claim_id="cX")


def test_losers_exclude_winner_preserving_order() -> None:
    """(2) claim_ids [c1,c2,c3], winner c2 → losers == (c1, c3)."""
    contra = _contradiction(["c1", "c2", "c3"], ["e1", "e2"])
    plan = plan_resolution(contra, winner_claim_id="c2")
    assert plan.loser_claim_ids == ("c1", "c3")


def test_node_patch_status_and_resolution() -> None:
    """(3) node_patch помечает resolved и ссылается на победителя."""
    contra = _contradiction(["c1", "c2", "c3"], ["e1", "e2"])
    plan = plan_resolution(contra, winner_claim_id="c2")
    assert plan.node_patch["status"] == "resolved"
    assert plan.node_patch["resolution"] == "c2"


def test_edges_to_quench_equal_edge_list() -> None:
    """(4) edges_to_quench == список рёбер противоречия."""
    contra = _contradiction(["c1", "c2"], ["e1", "e2", "e3"])
    plan = plan_resolution(contra, winner_claim_id="c1")
    assert plan.edges_to_quench == ("e1", "e2", "e3")


def test_reason_threaded_into_node_patch() -> None:
    """(5) reason проброшен в node_patch['reason']."""
    contra = _contradiction(["c1", "c2"], ["e1"])
    plan = plan_resolution(contra, winner_claim_id="c1", reason="stronger provenance")
    assert plan.node_patch["reason"] == "stronger provenance"


def test_as_dict_contains_contradiction_id() -> None:
    """(6) as_dict() возвращает плоский dict с contradiction_id."""
    contra = _contradiction(["c1", "c2"], ["e1"])
    plan = plan_resolution(contra, winner_claim_id="c1")
    d = plan.as_dict()
    assert d["contradiction_id"] == "contra-1"
    assert isinstance(plan, ResolutionPlan)


def test_two_claim_contradiction_single_loser() -> None:
    """(7) Двухкларное противоречие, winner c1 → ровно один проигравший."""
    contra = _contradiction(["c1", "c2"], ["e1"])
    plan = plan_resolution(contra, winner_claim_id="c1")
    assert plan.loser_claim_ids == ("c2",)
    assert len(plan.loser_claim_ids) == 1
