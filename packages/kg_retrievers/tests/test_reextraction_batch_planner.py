"""Tests for §25.8 re-extraction batch planner (pure python, no store).

RU: Проверяем группировку ячеек по документу, ранжирование по ожидаемому выходу,
разрыв ничьих по doc_id, накопительное восстановление, пустой ввод и as_dict().
EN: Exercises grouping cells by document, ranking by expected yield, doc_id tie-break,
cumulative recovery, empty input and the as_dict() round-trip.
"""

from __future__ import annotations

import pytest

from kg_retrievers.reextraction_batch_planner import (
    ReextractionBatch,
    ReextractionPlan,
    plan_reextraction,
)


def _cell(doc_id: str, p: float, material: str = "MOF-5", prop: str = "bandgap") -> dict:
    """Build one near-miss cell dict with the spec's four keys."""
    return {"doc_id": doc_id, "p_extractor_missed": p, "material": material, "property": prop}


def test_tie_on_sum_breaks_by_doc_id() -> None:
    """(1) D1 (0.6,0.3)=0.9 ties D2 (0.9)=0.9 -> tie broken by doc_id, D1 first."""
    cells = [_cell("D1", 0.6), _cell("D1", 0.3), _cell("D2", 0.9)]
    plan = plan_reextraction(cells)
    assert plan.batches[0].doc_id == "D1"  # tie 0.9 == 0.9 -> "D1" < "D2"
    assert plan.batches[1].doc_id == "D2"


def test_higher_yield_doc_ranks_first() -> None:
    """(2) With D2=0.95 > D1=0.9, D2 becomes batches[0]; D1 sums to 0.9 over 2 cells."""
    cells = [_cell("D1", 0.6), _cell("D1", 0.3), _cell("D2", 0.95)]
    plan = plan_reextraction(cells)
    assert plan.batches[0].doc_id == "D2"
    d1 = next(b for b in plan.batches if b.doc_id == "D1")
    assert d1.n_cells == 2
    assert round(d1.expected_recovered, 1) == 0.9
    assert d1.expected_recovered == pytest.approx(0.9)


def test_total_expected_is_sum_of_all_p() -> None:
    """(3) total_expected equals the sum of every cell's p_extractor_missed."""
    cells = [_cell("D1", 0.6), _cell("D1", 0.3), _cell("D2", 0.95)]
    plan = plan_reextraction(cells)
    assert plan.total_expected == pytest.approx(0.6 + 0.3 + 0.95)


def test_cumulative_non_decreasing_last_equals_total() -> None:
    """(4) cumulative is non-decreasing and its last element equals total_expected."""
    cells = [_cell("D1", 0.6), _cell("D1", 0.3), _cell("D2", 0.95), _cell("D3", 0.1)]
    plan = plan_reextraction(cells)
    assert all(a <= b for a, b in zip(plan.cumulative, plan.cumulative[1:], strict=False))
    assert plan.cumulative[-1] == pytest.approx(plan.total_expected)


def test_len_batches_equals_distinct_doc_count() -> None:
    """(5) One batch per distinct doc_id, regardless of cell count."""
    cells = [_cell("D1", 0.2), _cell("D1", 0.2), _cell("D2", 0.3), _cell("D3", 0.4)]
    plan = plan_reextraction(cells)
    assert len(plan.batches) == 3
    assert {b.doc_id for b in plan.batches} == {"D1", "D2", "D3"}


def test_empty_cells_give_zero_total_and_empty_cumulative() -> None:
    """(6) Empty input -> no batches, total_expected 0.0, empty cumulative."""
    plan = plan_reextraction([])
    assert plan.batches == []
    assert plan.total_expected == 0.0
    assert plan.cumulative == []


def test_single_doc_yields_one_batch_matching_total() -> None:
    """(7) A single-doc input yields one batch whose recovery equals total_expected."""
    cells = [_cell("D1", 0.6), _cell("D1", 0.3)]
    plan = plan_reextraction(cells)
    assert len(plan.batches) == 1
    only = plan.batches[0]
    assert only.doc_id == "D1"
    assert only.expected_recovered == pytest.approx(plan.total_expected)
    assert plan.cumulative[-1] == pytest.approx(plan.total_expected)


def test_batches_sorted_descending_by_expected_recovered() -> None:
    """(8) Batches are ordered by descending expected_recovered."""
    cells = [_cell("A", 0.1), _cell("B", 0.5), _cell("C", 0.3)]
    plan = plan_reextraction(cells)
    recovered = [b.expected_recovered for b in plan.batches]
    assert recovered == sorted(recovered, reverse=True)
    assert [b.doc_id for b in plan.batches] == ["B", "C", "A"]


def test_as_dict_round_trip() -> None:
    """(9) as_dict() projections mirror the dataclass fields for JSON dump."""
    cells = [_cell("D1", 0.6), _cell("D2", 0.9)]
    plan = plan_reextraction(cells)
    d = plan.as_dict()
    assert d["total_expected"] == pytest.approx(plan.total_expected)
    assert d["cumulative"] == plan.cumulative
    assert d["batches"][0] == plan.batches[0].as_dict()
    assert set(d["batches"][0]) == {"doc_id", "n_cells", "expected_recovered"}


def test_frozen_dataclasses_are_immutable() -> None:
    """(10) Both dataclasses are frozen (attribute assignment raises)."""
    batch = ReextractionBatch(doc_id="D1", n_cells=1, expected_recovered=0.5)
    plan = ReextractionPlan(batches=[batch], total_expected=0.5, cumulative=[0.5])
    with pytest.raises(AttributeError):
        batch.doc_id = "X"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        plan.total_expected = 1.0  # type: ignore[misc]
