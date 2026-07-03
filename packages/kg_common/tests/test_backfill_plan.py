"""Partitions backfill planning tests (§9.3).

Hand-checked: every pending list, batch shape, and per-key gate result is
spelled out against the spec assertions.
"""

from __future__ import annotations

from kg_common.backfill_plan import BackfillPlan, needs_backfill, plan_backfill


def test_pending_skips_completed_keys() -> None:
    assert plan_backfill(("a", "b", "c"), {"a"}).pending == ("b", "c")


def test_failed_key_rerun_even_if_completed() -> None:
    plan = plan_backfill(("a", "b"), {"a", "b"}, failed={"a"})
    # 'a' is completed but failed => re-run; 'b' completed and not failed => skip.
    assert plan.pending == ("a",)


def test_needs_backfill_completed_not_failed_is_false() -> None:
    assert needs_backfill("x", {"x"}, set()) is False


def test_needs_backfill_completed_and_failed_is_true() -> None:
    assert needs_backfill("x", {"x"}, {"x"}) is True


def test_needs_backfill_not_completed_is_true() -> None:
    assert needs_backfill("y", set(), set()) is True


def test_batches_chunked_by_batch_size() -> None:
    plan = plan_backfill(("a", "b", "c", "d", "e"), set(), batch_size=2)
    assert [len(b) for b in plan.batches] == [2, 2, 1]
    assert plan.batches == (("a", "b"), ("c", "d"), ("e",))


def test_batch_size_zero_is_single_batch() -> None:
    assert plan_backfill(("a", "b"), set(), batch_size=0).batches == (("a", "b"),)


def test_empty_pending_yields_empty_batches() -> None:
    plan = plan_backfill(("a",), {"a"})
    assert plan.pending == ()
    assert plan.batches == ()


def test_duplicates_deduped_preserving_order() -> None:
    assert plan_backfill(("a", "a", "b"), set()).pending == ("a", "b")


def test_order_preserved_from_input() -> None:
    plan = plan_backfill(("c", "a", "b"), {"a"})
    assert plan.pending == ("c", "b")


def test_as_dict_json_friendly() -> None:
    plan = plan_backfill(("a", "b", "c"), set(), batch_size=2, name="parts")
    assert plan.as_dict() == {
        "name": "parts",
        "pending": ["a", "b", "c"],
        "batches": [["a", "b"], ["c"]],
    }


def test_backfill_plan_is_frozen() -> None:
    plan = BackfillPlan(name="n", pending=("a",), batches=(("a",),))
    try:
        plan.name = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("BackfillPlan should be frozen")


def test_dedup_failed_only_counted_once() -> None:
    # Duplicate failed key appears once, in first-seen order.
    plan = plan_backfill(("a", "b", "a"), {"a", "b"}, failed={"a"})
    assert plan.pending == ("a",)
    assert plan.batches == (("a",),)
