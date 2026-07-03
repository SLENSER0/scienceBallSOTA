"""Tests for §11.7 multi-batch map-context planning.

Тесты жадного (greedy) наполнения пакетов под лимитом токенов на контекст.
Все ожидаемые значения посчитаны вручную (hand-checkable).
"""

from __future__ import annotations

from kg_retrievers.community_map_batches import BatchPlan, MapBatch, plan_batches


def _report(cid: str, score: float, tokens: int) -> dict:
    """Build one report mapping ``{community_id, score, est_tokens}``."""
    return {"community_id": cid, "score": score, "est_tokens": tokens}


def test_under_limit_single_batch() -> None:
    # 100 + 200 + 150 = 450 <= 1000 → one batch.
    reports = [
        _report("a", 0.9, 100),
        _report("b", 0.8, 200),
        _report("c", 0.7, 150),
    ]
    plan = plan_batches(reports, max_context_tokens=1000)
    assert plan.n_batches == 1
    assert plan.batches[0].tokens == 450
    assert plan.batches[0].community_ids == ("a", "b", "c")
    assert plan.dropped == ()


def test_overflow_two_batches() -> None:
    # 600 + 500 = 1100 > 1000 → second report starts batch 1.
    reports = [
        _report("a", 0.9, 600),
        _report("b", 0.8, 500),
    ]
    plan = plan_batches(reports, max_context_tokens=1000)
    assert plan.n_batches == 2
    assert plan.batches[0].community_ids == ("a",)
    assert plan.batches[0].tokens == 600
    assert plan.batches[1].community_ids == ("b",)
    assert plan.batches[1].tokens == 500


def test_oversized_report_dropped() -> None:
    reports = [
        _report("a", 0.9, 300),
        _report("big", 0.8, 5000),  # est_tokens > limit → dropped
        _report("c", 0.7, 200),
    ]
    plan = plan_batches(reports, max_context_tokens=1000)
    assert "big" in plan.dropped
    assert plan.n_batches == 1
    assert plan.batches[0].community_ids == ("a", "c")
    assert plan.batches[0].tokens == 500


def test_every_batch_within_limit() -> None:
    reports = [_report(f"c{i}", 1.0 - i * 0.05, 400) for i in range(7)]
    plan = plan_batches(reports, max_context_tokens=1000)
    for batch in plan.batches:
        assert batch.tokens <= 1000
    # 7 * 400 = 2800; each batch holds 2 (800), so 4 batches: 800,800,800,400.
    assert plan.n_batches == 4
    assert [b.tokens for b in plan.batches] == [800, 800, 800, 400]


def test_ordering_highest_score_in_batch_zero() -> None:
    # Given out of order; top score is "z" (0.99) → must lead batch 0.
    reports = [
        _report("m", 0.5, 100),
        _report("z", 0.99, 100),
        _report("a", 0.7, 100),
    ]
    plan = plan_batches(reports, max_context_tokens=1000)
    assert plan.batches[0].community_ids[0] == "z"
    # tie-break: order should be z (0.99), a (0.7), m (0.5).
    assert plan.batches[0].community_ids == ("z", "a", "m")


def test_score_tie_breaks_by_community_id() -> None:
    reports = [
        _report("b", 0.5, 100),
        _report("a", 0.5, 100),
        _report("c", 0.5, 100),
    ]
    plan = plan_batches(reports, max_context_tokens=1000)
    assert plan.batches[0].community_ids == ("a", "b", "c")


def test_max_batches_drops_second_batch_ids() -> None:
    reports = [
        _report("a", 0.9, 600),
        _report("b", 0.8, 500),  # would be batch 1
    ]
    plan = plan_batches(reports, max_context_tokens=1000, max_batches=1)
    assert plan.n_batches == 1
    assert plan.batches[0].community_ids == ("a",)
    assert "b" in plan.dropped


def test_empty_reports() -> None:
    plan = plan_batches([], max_context_tokens=1000)
    assert plan.n_batches == 0
    assert plan.batches == ()
    assert plan.dropped == ()


def test_partition_invariant_each_id_once() -> None:
    # Mix of packable and oversized, with a max_batches cap.
    reports = [
        _report("a", 0.9, 400),
        _report("b", 0.85, 400),
        _report("big", 0.8, 9000),  # dropped: too large
        _report("c", 0.7, 400),
        _report("d", 0.6, 400),
        _report("e", 0.5, 400),
    ]
    plan = plan_batches(reports, max_context_tokens=1000, max_batches=2)
    placed = [cid for batch in plan.batches for cid in batch.community_ids]
    all_ids = placed + list(plan.dropped)
    # every input id appears exactly once across batches ∪ dropped
    assert sorted(all_ids) == ["a", "b", "big", "c", "d", "e"]
    assert len(all_ids) == len(set(all_ids))
    assert "big" in plan.dropped


def test_as_dict_shapes() -> None:
    reports = [_report("a", 0.9, 100), _report("b", 0.8, 200)]
    plan = plan_batches(reports, max_context_tokens=1000)
    assert isinstance(plan, BatchPlan)
    assert isinstance(plan.batches[0], MapBatch)
    d = plan.as_dict()
    assert d == {
        "batches": [{"index": 0, "community_ids": ["a", "b"], "tokens": 300}],
        "n_batches": 1,
        "dropped": [],
    }
    assert plan.batches[0].as_dict() == {
        "index": 0,
        "community_ids": ["a", "b"],
        "tokens": 300,
    }


def test_frozen_dataclasses() -> None:
    plan = plan_batches([_report("a", 0.9, 100)], max_context_tokens=1000)
    import dataclasses

    with_batch = plan.batches[0]
    for target in (plan, with_batch):
        try:
            dataclasses.replace(target)  # frozen still allows replace
        except Exception:  # pragma: no cover - defensive
            raise
    for target, field in ((plan, "n_batches"), (with_batch, "tokens")):
        try:
            setattr(target, field, 999)
            raise AssertionError("expected FrozenInstanceError")
        except dataclasses.FrozenInstanceError:
            pass
