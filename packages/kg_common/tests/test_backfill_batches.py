"""Tests for backfill run batching — тесты нарезки добора (§9.3)."""

from __future__ import annotations

import pytest

from kg_common.backfill_batches import (
    BackfillBatch,
    backfill_summary,
    chunk_partitions,
)


def test_batch_size_two_over_five_keys_gives_sizes_2_2_1() -> None:
    keys = ["a", "b", "c", "d", "e"]
    batches = chunk_partitions(keys, 2)
    assert len(batches) == 3
    assert tuple(b.size for b in batches) == (2, 2, 1)


def test_batch_indices_are_sequential() -> None:
    batches = chunk_partitions(["a", "b", "c", "d", "e"], 2)
    assert [b.index for b in batches] == [0, 1, 2]


def test_last_batch_holds_trailing_partitions() -> None:
    batches = chunk_partitions(["a", "b", "c", "d", "e"], 2)
    assert batches[0].partition_keys == ("a", "b")
    assert batches[1].partition_keys == ("c", "d")
    assert batches[-1].partition_keys == ("e",)


def test_batch_size_larger_than_input_is_single_batch() -> None:
    keys = ["a", "b", "c"]
    batches = chunk_partitions(keys, 10)
    assert len(batches) == 1
    assert batches[0].partition_keys == ("a", "b", "c")
    assert batches[0].index == 0


def test_empty_input_yields_empty_tuple() -> None:
    assert chunk_partitions([], 2) == ()


def test_batch_size_zero_raises_value_error() -> None:
    with pytest.raises(ValueError):
        chunk_partitions(["a", "b"], 0)


def test_batch_size_negative_raises_value_error() -> None:
    with pytest.raises(ValueError):
        chunk_partitions(["a"], -1)


def test_summary_totals_and_max() -> None:
    batches = chunk_partitions(["a", "b", "c", "d", "e"], 2)
    summary = backfill_summary(batches)
    total_from_sizes = sum(b.size for b in batches)
    assert summary["batches"] == 3
    assert summary["total_partitions"] == total_from_sizes == 5
    assert summary["max_batch_size"] == 2


def test_summary_of_empty_is_zeroed() -> None:
    summary = backfill_summary([])
    assert summary == {"batches": 0, "total_partitions": 0, "max_batch_size": 0}


def test_as_dict_and_size_property() -> None:
    batches = chunk_partitions(["a", "b", "c", "d", "e"], 2)
    first = batches[0]
    assert first.as_dict()["index"] == 0
    assert first.size == len(first.partition_keys) == 2
    assert first.as_dict()["size"] == first.size


def test_order_across_batches_reconstructs_original() -> None:
    keys = ["p0", "p1", "p2", "p3", "p4", "p5", "p6"]
    batches = chunk_partitions(keys, 3)
    rebuilt: list[str] = []
    for batch in batches:
        rebuilt.extend(batch.partition_keys)
    assert rebuilt == keys


def test_batch_is_frozen() -> None:
    batch = BackfillBatch(index=0, partition_keys=("a",))
    with pytest.raises(AttributeError):
        batch.index = 1  # type: ignore[misc]
